import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ElementTree
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Set, Tuple, TypeVar

from lighthouse_tool import credentials, limits, process_tree
from lighthouse_tool import repo as repository
from lighthouse_tool.records import write_atomically
from lighthouse_tool.repo import Parser, Refusal, checked_git, require_root

Outcome = Tuple[int, Optional[str], Optional[str]]
BUILDS = ("core", "feature")
PREPARATION_STEPS = ("setup", "build")
SUITE_STEPS = ("suite", "rerun")
UNRUNNABLE_EXITS = (126, 127)
WHOLE_SUITE = "suite"
OWNER_MARK = "lighthouse-owned"
COMMITS = "commits.json"
CORE_STORE = "core-suites"
STORED_SUITE_FIELDS = ("command", "junit", "rerun", "timeout_minutes")
RERUN_PLACEHOLDER = re.compile(r"\{(tests|names_regex|names)\}")
SHELL_PIECE = re.compile(r"""\\.|'[^']*'?|"(?:\\.|[^"\\])*"?|[^\\'"]+""", re.S)
Timed = TypeVar("Timed")


class StepRun(NamedTuple):
    exit: Optional[int]
    problem: Optional[str]


class SuiteRun(NamedTuple):
    exit: Optional[int]
    problem: Optional[str]
    tests: Optional[Dict[str, bool]]
    names: Optional[Dict[str, str]] = None


class Report(NamedTuple):
    tests: Dict[str, bool]
    names: Dict[str, str]


class Classification(NamedTuple):
    failures: List[str]
    pre_existing: List[str]
    flaky: List[str]


class CoreBuild(NamedTuple):
    problem: Optional[str]
    run: Optional[SuiteRun]
    summary: Optional[Dict[str, Any]]


class FeatureBuild(NamedTuple):
    problem: Optional[str]
    first: Optional[SuiteRun]
    prepare_minutes: float
    suite_minutes: float


NOTHING_FOUND = Classification([], [], [])


def parser(subcommand: str) -> Parser:
    arguments = Parser(prog="lighthouse " + subcommand, add_help=False)
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--results", required=True)
    if subcommand != "release":
        arguments.add_argument("--core", required=True)
        arguments.add_argument("--feature", required=True)
    if subcommand == "suite":
        arguments.add_argument("--profile")
    return arguments


def run(argv: List[str]) -> Outcome:
    subcommand = argv[0]
    try:
        options = parser(subcommand).parse_args(argv[1:])
        result = SUBCOMMANDS[subcommand](options)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse {}: {}".format(subcommand, refusal)
    return 0, json.dumps(result), None


def worktrees_command(options: argparse.Namespace) -> Dict[str, Any]:
    return make_worktrees(require_root(options.repo), options.core, options.feature, options.results)


def release_command(options: argparse.Namespace) -> Dict[str, Any]:
    return release_worktrees(require_root(options.repo), options.results)


def suite_command(options: argparse.Namespace) -> Dict[str, Any]:
    root = require_root(options.repo)
    worktrees = make_worktrees(root, options.core, options.feature, options.results)
    profile = chosen_profile(root, worktrees["feature"]["path"], options.profile)
    folder = os.path.realpath(options.results)
    store = core_store_path(root, profile, worktrees["core"]["commit"])
    result = compare_builds(profile, hidden_values(root, profile), folder, worktrees, store)
    with open(os.path.join(folder, "suite.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    return result


def resolved(root: str, branch: str) -> str:
    commit = repository.resolve_branch(root, branch)
    if commit is None:
        raise Refusal("branch {} does not exist locally or on origin".format(branch))
    return commit


def is_inside(root: str, path: str) -> bool:
    folder, base = os.path.realpath(path), os.path.realpath(root)
    return folder == base or folder.startswith(base + os.sep)


def make_worktrees(root: str, core: str, feature: str, results: str) -> Dict[str, Dict[str, str]]:
    if is_inside(root, results):
        raise Refusal("the results folder {} is inside the repository {}; choose a folder outside it".format(results, root))
    commits = {"core": resolved(root, core), "feature": resolved(root, feature)}
    os.makedirs(results, exist_ok=True)
    folder = os.path.realpath(results)
    listed = listed_worktrees(root)
    placed = {build: place_worktree(root, os.path.join(folder, build), commits[build], listed) for build in BUILDS}
    write_commits(folder, commits)
    return placed


def write_commits(folder: str, commits: Dict[str, str]) -> None:
    with open(os.path.join(folder, COMMITS), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(commits) + "\n")


def listed_worktrees(root: str) -> List[str]:
    porcelain = checked_git(root, ["worktree", "list", "--porcelain"])
    prefix = "worktree "
    return [os.path.realpath(line[len(prefix):]) for line in porcelain.splitlines() if line.startswith(prefix)]


def place_worktree(root: str, path: str, commit: str, listed: List[str]) -> Dict[str, str]:
    registered = path in listed
    if registered and os.path.isdir(path):
        if not is_owned(path):
            raise Refusal("{} is a worktree lighthouse did not create; choose another --results folder".format(path))
        checked_git(path, ["checkout", "--detach", "--force", commit])
    else:
        replacing_a_vanished_one = ["--force"] if registered else []
        checked_git(root, ["worktree", "add", *replacing_a_vanished_one, "--detach", path, commit])
        mark_owned(path)
    return {"path": path, "commit": commit}


def administrative_folder(path: str) -> Optional[str]:
    code, stdout, _ = repository.git(path, ["rev-parse", "--absolute-git-dir"])
    return stdout.strip() if code == 0 else None


def is_owned(path: str) -> bool:
    folder = administrative_folder(path)
    return folder is not None and os.path.isfile(os.path.join(folder, OWNER_MARK))


def mark_owned(path: str) -> None:
    folder = administrative_folder(path)
    if folder is None:
        raise Refusal("cannot find the git folder of the new worktree {}".format(path))
    open(os.path.join(folder, OWNER_MARK), "w", encoding="utf-8").close()


def release_worktrees(root: str, results: str) -> Dict[str, List[str]]:
    folder = os.path.realpath(results)
    listed = listed_worktrees(root)
    candidates = [os.path.join(folder, build) for build in BUILDS]
    targets = [path for path in candidates if path in listed and os.path.isdir(path) and is_owned(path)]
    for path in targets:
        checked_git(root, ["worktree", "remove", "--force", path])
    checked_git(root, ["worktree", "prune"])
    return {"removed": targets}


def chosen_profile(root: str, feature_path: str, path: Optional[str]) -> Dict[str, Any]:
    if path is not None:
        profile = repository.load_profile(root, path)
        if profile is None:
            raise Refusal("profile {} is missing or not JSON".format(path))
    else:
        feature_profile = repository.load_profile(root, os.path.join(feature_path, ".lighthouse", "profile.json"))
        profile = feature_profile if feature_profile is not None else repository.load_profile(root)
        if profile is None:
            raise Refusal("no profile: neither the FEATURE branch nor the repository has .lighthouse/profile.json")
    if not isinstance(profile, dict) or step_command(profile, "suite") is None:
        raise Refusal("the profile records no suite command")
    return profile


def step_command(profile: Dict[str, Any], step: str) -> Optional[str]:
    section = profile.get(step)
    command = section.get("command") if isinstance(section, dict) else None
    return command if isinstance(command, str) and command.strip() else None


def junit_report(profile: Dict[str, Any]) -> Optional[str]:
    junit = profile["suite"].get("junit")
    return junit if isinstance(junit, str) and junit.strip() else None


def rerun_template(profile: Dict[str, Any]) -> Optional[str]:
    rerun = profile["suite"].get("rerun")
    return rerun if isinstance(rerun, str) and rerun.strip() else None


def runs_isolated(profile: Dict[str, Any]) -> bool:
    return profile["suite"].get("isolated") is True


def step_limit(step: str, profile: Dict[str, Any]) -> float:
    found = limits.of(profile)
    if step in PREPARATION_STEPS:
        return found.build_seconds
    if step in SUITE_STEPS:
        return found.suite_seconds
    return found.check_seconds


def hidden_values(root: str, profile: Dict[str, Any]) -> credentials.Secrets:
    return credentials.reachable_secrets(root, (repository.load_profile(root), profile))


def run_step(
    step: str, command: str, worktree: str, build: str, log_path: str, profile: Dict[str, Any], hidden: credentials.Secrets
) -> StepRun:
    seconds = step_limit(step, profile)
    append_log(log_path, "$ {}: {}\n".format(step, command), hidden)
    with tempfile.TemporaryFile() as output:
        try:
            process = process_tree.start(
                ["/bin/sh", "-c", command],
                cwd=worktree,
                env={**os.environ, "LIGHTHOUSE_BUILD": build},
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        except OSError as error:
            return StepRun(None, "{} could not start: {}".format(step, error.strerror or error))
        with process_tree.owned(process):
            try:
                process_tree.exited_unreaped(process, seconds)
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
        outcome = (
            StepRun(None, "{} timed out after its limit of {:g} seconds".format(step, seconds))
            if timed_out
            else StepRun(process.returncode, None)
        )
        output.seek(0)
        append_log(log_path, output.read().decode("utf-8", errors="replace"), hidden)
    return outcome


def append_log(log_path: str, text: str, hidden: credentials.Secrets) -> None:
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(credentials.redacted(text, hidden))


def prepare(
    profile: Dict[str, Any], hidden: credentials.Secrets, worktree: str, build: str, log_path: str
) -> Optional[str]:
    for step in PREPARATION_STEPS:
        command = step_command(profile, step)
        if command is None:
            continue
        outcome = run_step(step, command, worktree, build, log_path, profile, hidden)
        if outcome.problem is not None:
            return outcome.problem
        if outcome.exit != 0:
            return "{} exited {}".format(step, outcome.exit)
    return None


def run_suite(profile: Dict[str, Any], hidden: credentials.Secrets, worktree: str, build: str, log_path: str) -> SuiteRun:
    junit = junit_report(profile)
    report = os.path.join(worktree, junit) if junit else None
    if report is not None:
        discard(report)
    outcome = run_step("suite", step_command(profile, "suite") or "", worktree, build, log_path, profile, hidden)
    if outcome.problem is not None:
        return SuiteRun(None, outcome.problem, None)
    if outcome.exit in UNRUNNABLE_EXITS:
        return SuiteRun(outcome.exit, "the suite command could not run: exit {}".format(outcome.exit), None)
    if report is None:
        return SuiteRun(outcome.exit, None, None)
    found = read_report(report)
    if found is None:
        return SuiteRun(outcome.exit, "the JUnit report {} is missing or unreadable after the suite ran".format(junit), None)
    return SuiteRun(outcome.exit, None, with_exit_status(found.tests, outcome.exit), found.names)


def with_exit_status(tests: Dict[str, bool], exit_status: Optional[int]) -> Dict[str, bool]:
    unexplained_exit = exit_status != 0 and not any(tests.values())
    return {**tests, WHOLE_SUITE: True} if unexplained_exit else tests


def discard(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def read_report(path: str) -> Optional[Report]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return None
    cases = [case for case in root.iter("testcase") if case.find("skipped") is None]
    failed = {case_id(case) for case in cases if case_failed(case)}
    return Report(
        tests={case_id(case): case_id(case) in failed for case in cases},
        names={case_id(case): case.get("name") or "" for case in cases},
    )


def case_id(case: ElementTree.Element) -> str:
    classname = case.get("classname") or ""
    name = case.get("name") or ""
    return "{}.{}".format(classname, name) if classname else name


def case_failed(case: ElementTree.Element) -> bool:
    return case.find("failure") is not None or case.find("error") is not None


def failed_ids(run: Optional[SuiteRun]) -> Set[str]:
    tests = run.tests if run is not None and run.tests is not None else {}
    return {test_id for test_id, has_failed in tests.items() if has_failed}


def has_failures(run: SuiteRun) -> bool:
    return bool(failed_ids(run)) if run.tests is not None else run.exit != 0


def classify_by_test(first: SuiteRun, second: SuiteRun, baseline: Optional[SuiteRun]) -> Classification:
    first_failed = failed_ids(first)
    repeated = first_failed & failed_ids(second)
    core_failed = failed_ids(baseline)
    return Classification(
        failures=sorted(repeated - core_failed),
        pre_existing=sorted(repeated & core_failed),
        flaky=sorted(first_failed - repeated),
    )


def classify_by_exit(second: SuiteRun, baseline: Optional[SuiteRun]) -> Classification:
    if second.exit == 0:
        return Classification([], [], [WHOLE_SUITE])
    if baseline is not None and baseline.exit != 0:
        return Classification([], [WHOLE_SUITE], [])
    return Classification([WHOLE_SUITE], [], [])


def no_baseline_reason(core_problem: Optional[str], core_run: Optional[SuiteRun]) -> Optional[str]:
    if core_problem is not None:
        return "core did not build ({}), so there is no baseline and every FEATURE failure counts".format(core_problem)
    if core_run is not None and core_run.problem is not None:
        return "core's suite did not run ({}), so there is no baseline and every FEATURE failure counts".format(
            core_run.problem
        )
    return None


def timed(action: Callable[[], Timed]) -> Tuple[Timed, float]:
    started = time.monotonic()
    outcome = action()
    return outcome, round((time.monotonic() - started) / 60, 3)


def build_summary(run: SuiteRun, log_path: str, prepare_minutes: float, suite_minutes: float) -> Dict[str, Any]:
    return {"exit": run.exit, "log": log_path, "prepare_minutes": prepare_minutes, "suite_minutes": suite_minutes}


def recorded_tests(tests: Optional[Dict[str, bool]]) -> Optional[Dict[str, List[str]]]:
    if tests is None:
        return None
    return {
        "passed": sorted(test_id for test_id, has_failed in tests.items() if not has_failed),
        "failed": sorted(test_id for test_id, has_failed in tests.items() if has_failed),
    }


def suite_result(
    result: str,
    reason: Optional[str],
    found: Classification,
    core: Optional[Dict[str, Any]],
    feature: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "result": result,
        "reason": reason,
        "failures": found.failures,
        "pre_existing": found.pre_existing,
        "flaky": found.flaky,
        "core": core,
        "feature": feature,
    }


def core_suite_key(profile: Dict[str, Any], commit: str) -> str:
    suite = profile["suite"]
    identity = {
        "commit": commit,
        "setup": step_command(profile, "setup"),
        "build": step_command(profile, "build"),
        "suite": {field: suite.get(field) for field in STORED_SUITE_FIELDS},
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()


def core_store_path(root: str, profile: Dict[str, Any], commit: str) -> Optional[str]:
    try:
        folder = repository.ensure_state_dir(root)
    except Refusal:
        return None
    return None if folder is None else os.path.join(folder, CORE_STORE, core_suite_key(profile, commit) + ".json")


def is_test_outcomes(tests: Any) -> bool:
    return tests is None or (isinstance(tests, dict) and all(isinstance(value, bool) for value in tests.values()))


def stored_core(store: Optional[str]) -> Optional[Tuple[SuiteRun, str, Optional[Dict[str, bool]]]]:
    if store is None:
        return None
    try:
        with open(store, encoding="utf-8") as handle:
            entry = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(entry, dict):
        return None
    exit_status, tests, log = entry.get("exit"), entry.get("tests"), entry.get("log")
    first_tests = entry.get("first_tests")
    usable = (
        (exit_status is None or (isinstance(exit_status, int) and not isinstance(exit_status, bool)))
        and is_test_outcomes(tests)
        and is_test_outcomes(first_tests)
        and isinstance(log, str)
    )
    return (SuiteRun(exit_status, None, tests), log, first_tests) if usable else None


def store_core(store: Optional[str], run: SuiteRun, log_path: str, first: SuiteRun) -> None:
    if store is None:
        return
    with open(log_path, encoding="utf-8") as log:
        entry = {"exit": run.exit, "tests": run.tests, "first_tests": first.tests, "log": log.read()}
    folder = os.path.dirname(store)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    write_atomically(store, json.dumps(entry) + "\n")


def confirmed_failures(first: SuiteRun, second: SuiteRun) -> SuiteRun:
    if first.tests is None:
        return SuiteRun(first.exit if second.exit != 0 else 0, None, None)
    repeated = failed_ids(second)
    tests = {test_id: has_failed and test_id in repeated for test_id, has_failed in first.tests.items()}
    return SuiteRun(first.exit if any(tests.values()) else 0, None, tests)


def quoted_placeholders(template: str) -> List[str]:
    return [
        placeholder.group(0)
        for piece in SHELL_PIECE.finditer(template)
        if piece.group(0)[0] in "'\""
        for placeholder in RERUN_PLACEHOLDER.finditer(piece.group(0))
    ]


def filled_rerun(template: str, failing: List[str], names: Dict[str, str]) -> str:
    chosen = [names[test_id] for test_id in failing]
    values = {
        "tests": " ".join(shlex.quote(test_id) for test_id in failing),
        "names": " ".join(shlex.quote(name) for name in chosen),
        "names_regex": shlex.quote("^({})$".format("|".join(re.escape(name) for name in chosen))),
    }
    return RERUN_PLACEHOLDER.sub(lambda placeholder: values[placeholder.group(1)], template)


def run_failed_tests(
    profile: Dict[str, Any], hidden: credentials.Secrets, worktree: str, build: str, log_path: str, first: SuiteRun
) -> Optional[SuiteRun]:
    template = rerun_template(profile)
    junit = junit_report(profile)
    names = first.names or {}
    failing = sorted(failed_ids(first))
    if template is None or quoted_placeholders(template) or junit is None or not failing:
        return None
    if any(test_id not in names for test_id in failing):
        return None
    report = os.path.join(worktree, junit)
    discard(report)
    outcome = run_step("rerun", filled_rerun(template, failing, names), worktree, build, log_path, profile, hidden)
    if outcome.problem is not None or outcome.exit in UNRUNNABLE_EXITS:
        return None
    found = read_report(report)
    if found is None or any(test_id not in found.tests for test_id in failing):
        return None
    return SuiteRun(outcome.exit, None, with_exit_status(found.tests, outcome.exit), found.names)


def rerun_suite(
    profile: Dict[str, Any], hidden: credentials.Secrets, worktree: str, build: str, log_path: str, first: SuiteRun
) -> SuiteRun:
    targeted = run_failed_tests(profile, hidden, worktree, build, log_path, first)
    return targeted if targeted is not None else run_suite(profile, hidden, worktree, build, log_path)


def reused_core(stored: Tuple[SuiteRun, str, Optional[Dict[str, bool]]], log_path: str) -> CoreBuild:
    run, log, first_tests = stored
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(log)
    summary = {
        **build_summary(run, log_path, 0.0, 0.0),
        "rerun_minutes": None,
        "reused": True,
        "tests": recorded_tests(first_tests),
    }
    return CoreBuild(None, run, summary)


def confirmed_core(
    profile: Dict[str, Any], hidden: credentials.Secrets, worktree: str, log_path: str, first: SuiteRun
) -> Tuple[SuiteRun, Optional[float], bool]:
    if first.problem is not None:
        return first, None, False
    if not has_failures(first):
        return first, None, True
    reran, rerun_minutes = timed(lambda: rerun_suite(profile, hidden, worktree, "core", log_path, first))
    if reran.problem is not None:
        return first, rerun_minutes, False
    return confirmed_failures(first, reran), rerun_minutes, True


def core_build(
    profile: Dict[str, Any], hidden: credentials.Secrets, worktree: str, log_path: str, store: Optional[str]
) -> CoreBuild:
    stored = stored_core(store)
    if stored is not None:
        return reused_core(stored, log_path)
    problem, prepare_minutes = timed(lambda: prepare(profile, hidden, worktree, "core", log_path))
    if problem is not None:
        return CoreBuild(problem, None, None)
    first, suite_minutes = timed(lambda: run_suite(profile, hidden, worktree, "core", log_path))
    baseline, rerun_minutes, storable = confirmed_core(profile, hidden, worktree, log_path, first)
    if storable:
        store_core(store, baseline, log_path, first)
    summary = {
        **build_summary(baseline, log_path, prepare_minutes, suite_minutes),
        "rerun_minutes": rerun_minutes,
        "reused": False,
        "tests": recorded_tests(first.tests),
    }
    return CoreBuild(None, baseline, summary)


def feature_build(profile: Dict[str, Any], hidden: credentials.Secrets, worktree: str, log_path: str) -> FeatureBuild:
    problem, prepare_minutes = timed(lambda: prepare(profile, hidden, worktree, "feature", log_path))
    if problem is not None:
        return FeatureBuild(problem, None, prepare_minutes, 0.0)
    first, suite_minutes = timed(lambda: run_suite(profile, hidden, worktree, "feature", log_path))
    return FeatureBuild(None, first, prepare_minutes, suite_minutes)


def both_builds(
    profile: Dict[str, Any],
    hidden: credentials.Secrets,
    worktrees: Dict[str, Dict[str, str]],
    logs: Dict[str, str],
    store: Optional[str],
) -> Tuple[CoreBuild, FeatureBuild]:
    def build_core() -> CoreBuild:
        return core_build(profile, hidden, worktrees["core"]["path"], logs["core"], store)

    def build_feature() -> FeatureBuild:
        return feature_build(profile, hidden, worktrees["feature"]["path"], logs["feature"])

    if not runs_isolated(profile):
        core_built = build_core()
        return core_built, build_feature()
    with ThreadPoolExecutor(max_workers=len(BUILDS)) as pool:
        core_future = pool.submit(build_core)
        feature_future = pool.submit(build_feature)
        return core_future.result(), feature_future.result()


def compare_builds(
    profile: Dict[str, Any],
    hidden: credentials.Secrets,
    folder: str,
    worktrees: Dict[str, Dict[str, str]],
    store: Optional[str] = None,
) -> Dict[str, Any]:
    logs = {build: os.path.join(folder, "suite-{}.log".format(build)) for build in BUILDS}
    for log_path in logs.values():
        open(log_path, "w", encoding="utf-8").close()
    feature_path = worktrees["feature"]["path"]
    core_built, feature_built = both_builds(profile, hidden, worktrees, logs, store)
    core = core_built.summary
    first = feature_built.first
    if first is None:
        return suite_result("blocked", "FEATURE did not build: {}".format(feature_built.problem), NOTHING_FOUND, core, None)
    feature = {
        **build_summary(first, logs["feature"], feature_built.prepare_minutes, feature_built.suite_minutes),
        "rerun_minutes": None,
        "tests": recorded_tests(first.tests),
    }
    if first.problem is not None:
        return suite_result("blocked", "FEATURE's suite cannot run: " + first.problem, NOTHING_FOUND, core, feature)
    baseline_reason = no_baseline_reason(core_built.problem, core_built.run)
    if not has_failures(first):
        return suite_result("passed", baseline_reason, NOTHING_FOUND, core, feature)
    second, rerun_minutes = timed(
        lambda: rerun_suite(profile, hidden, feature_path, "feature", logs["feature"], first)
    )
    feature = {**feature, "rerun_minutes": rerun_minutes}
    if second.problem is not None:
        return suite_result(
            "blocked", "FEATURE's suite cannot run on its rerun: " + second.problem, NOTHING_FOUND, core, feature
        )
    baseline = core_built.run if baseline_reason is None else None
    found = classify_by_test(first, second, baseline) if first.tests is not None else classify_by_exit(second, baseline)
    return suite_result("failures" if found.failures else "passed", baseline_reason, found, core, feature)


SUBCOMMANDS = {
    "worktrees": worktrees_command,
    "release": release_command,
    "suite": suite_command,
}
