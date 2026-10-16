import argparse
import json
import os
import signal
import subprocess
import xml.etree.ElementTree as ElementTree
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

from lighthouse_tool import repo as repository

Outcome = Tuple[int, Optional[str], Optional[str]]
BUILDS = ("core", "feature")
PREPARATION_STEPS = ("setup", "build")
UNRUNNABLE_EXITS = (126, 127)
WHOLE_SUITE = "suite"


class Refusal(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Refusal(message)


class StepRun(NamedTuple):
    exit: Optional[int]
    problem: Optional[str]


class SuiteRun(NamedTuple):
    exit: Optional[int]
    problem: Optional[str]
    tests: Optional[Dict[str, bool]]


class Classification(NamedTuple):
    failures: List[str]
    pre_existing: List[str]
    flaky: List[str]


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


def repository_root(repo: str) -> str:
    root = repository.toplevel(repo)
    if root is None:
        raise Refusal("{} is not a git repository".format(repo))
    return root


def checked_git(where: str, args: List[str]) -> str:
    code, stdout, stderr = repository.git(where, args)
    if code != 0:
        raise Refusal("git {} failed: {}".format(" ".join(args[:2]), stderr.strip()))
    return stdout


def worktrees_command(options: argparse.Namespace) -> Dict[str, Any]:
    return make_worktrees(repository_root(options.repo), options.core, options.feature, options.results)


def release_command(options: argparse.Namespace) -> Dict[str, Any]:
    return release_worktrees(repository_root(options.repo), options.results)


def suite_command(options: argparse.Namespace) -> Dict[str, Any]:
    root = repository_root(options.repo)
    worktrees = make_worktrees(root, options.core, options.feature, options.results)
    profile = chosen_profile(root, worktrees["feature"]["path"], options.profile)
    folder = os.path.realpath(options.results)
    result = compare_builds(profile, folder, worktrees)
    with open(os.path.join(folder, "suite.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    return result


def resolved(root: str, branch: str) -> str:
    commit = repository.resolve_branch(root, branch)
    if commit is None:
        raise Refusal("branch {} does not exist locally or on origin".format(branch))
    return commit


def make_worktrees(root: str, core: str, feature: str, results: str) -> Dict[str, Dict[str, str]]:
    commits = {"core": resolved(root, core), "feature": resolved(root, feature)}
    os.makedirs(results, exist_ok=True)
    folder = os.path.realpath(results)
    listed = listed_worktrees(root)
    return {build: place_worktree(root, os.path.join(folder, build), commits[build], listed) for build in BUILDS}


def listed_worktrees(root: str) -> List[str]:
    porcelain = checked_git(root, ["worktree", "list", "--porcelain"])
    prefix = "worktree "
    return [os.path.realpath(line[len(prefix):]) for line in porcelain.splitlines() if line.startswith(prefix)]


def place_worktree(root: str, path: str, commit: str, listed: List[str]) -> Dict[str, str]:
    if path in listed and os.path.isdir(path):
        checked_git(path, ["checkout", "--detach", "--force", commit])
    else:
        checked_git(root, ["worktree", "add", "--detach", path, commit])
    return {"path": path, "commit": commit}


def release_worktrees(root: str, results: str) -> Dict[str, List[str]]:
    folder = os.path.realpath(results)
    listed = listed_worktrees(root)
    targets = [path for path in (os.path.join(folder, build) for build in BUILDS) if path in listed]
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


def timeout_minutes(profile: Dict[str, Any]) -> Optional[float]:
    minutes = profile["suite"].get("timeout_minutes")
    usable = isinstance(minutes, (int, float)) and not isinstance(minutes, bool) and minutes > 0
    return minutes if usable else None


def run_step(step: str, command: str, worktree: str, build: str, log_path: str, minutes: Optional[float]) -> StepRun:
    with open(log_path, "a", encoding="utf-8") as log:
        log.write("$ {}: {}\n".format(step, command))
        log.flush()
        try:
            process = subprocess.Popen(
                ["/bin/sh", "-c", command],
                cwd=worktree,
                env={**os.environ, "LIGHTHOUSE_BUILD": build},
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            return StepRun(None, "{} could not start: {}".format(step, error.strerror or error))
        try:
            return StepRun(process.wait(timeout=minutes * 60 if minutes else None), None)
        except subprocess.TimeoutExpired:
            stop(process)
            return StepRun(None, "{} timed out after {} minutes".format(step, minutes))


def stop(process: "subprocess.Popen[Any]") -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()
    process.wait()


def prepare(profile: Dict[str, Any], worktree: str, build: str, log_path: str) -> Optional[str]:
    for step in PREPARATION_STEPS:
        command = step_command(profile, step)
        if command is None:
            continue
        outcome = run_step(step, command, worktree, build, log_path, timeout_minutes(profile))
        if outcome.problem is not None:
            return outcome.problem
        if outcome.exit != 0:
            return "{} exited {}".format(step, outcome.exit)
    return None


def run_suite(profile: Dict[str, Any], worktree: str, build: str, log_path: str) -> SuiteRun:
    junit = junit_report(profile)
    report = os.path.join(worktree, junit) if junit else None
    if report is not None:
        discard(report)
    outcome = run_step("suite", step_command(profile, "suite") or "", worktree, build, log_path, timeout_minutes(profile))
    if outcome.problem is not None:
        return SuiteRun(None, outcome.problem, None)
    if outcome.exit in UNRUNNABLE_EXITS:
        return SuiteRun(outcome.exit, "the suite command could not run: exit {}".format(outcome.exit), None)
    if report is None:
        return SuiteRun(outcome.exit, None, None)
    tests = read_report(report)
    if tests is None:
        return SuiteRun(outcome.exit, "the JUnit report {} is missing or unreadable after the suite ran".format(junit), None)
    return SuiteRun(outcome.exit, None, tests)


def discard(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def read_report(path: str) -> Optional[Dict[str, bool]]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return None
    outcomes = [(case_id(case), case_failed(case)) for case in root.iter("testcase") if case.find("skipped") is None]
    failed = {test_id for test_id, has_failed in outcomes if has_failed}
    return {test_id: test_id in failed for test_id, _ in outcomes}


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


def build_summary(run: Optional[SuiteRun], log_path: str) -> Optional[Dict[str, Any]]:
    return {"exit": run.exit, "log": log_path} if run is not None else None


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


def compare_builds(profile: Dict[str, Any], folder: str, worktrees: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    logs = {build: os.path.join(folder, "suite-{}.log".format(build)) for build in BUILDS}
    for log_path in logs.values():
        open(log_path, "w", encoding="utf-8").close()
    core_path = worktrees["core"]["path"]
    feature_path = worktrees["feature"]["path"]
    core_problem = prepare(profile, core_path, "core", logs["core"])
    core_run = run_suite(profile, core_path, "core", logs["core"]) if core_problem is None else None
    core = build_summary(core_run, logs["core"])
    feature_problem = prepare(profile, feature_path, "feature", logs["feature"])
    if feature_problem is not None:
        return suite_result("blocked", "FEATURE did not build: " + feature_problem, NOTHING_FOUND, core, None)
    first = run_suite(profile, feature_path, "feature", logs["feature"])
    feature = build_summary(first, logs["feature"])
    if first.problem is not None:
        return suite_result("blocked", "FEATURE's suite cannot run: " + first.problem, NOTHING_FOUND, core, feature)
    baseline_reason = no_baseline_reason(core_problem, core_run)
    if not has_failures(first):
        return suite_result("passed", baseline_reason, NOTHING_FOUND, core, feature)
    second = run_suite(profile, feature_path, "feature", logs["feature"])
    if second.problem is not None:
        return suite_result(
            "blocked", "FEATURE's suite cannot run on its rerun: " + second.problem, NOTHING_FOUND, core, feature
        )
    baseline = core_run if baseline_reason is None else None
    found = classify_by_test(first, second, baseline) if first.tests is not None else classify_by_exit(second, baseline)
    return suite_result("failures" if found.failures else "passed", baseline_reason, found, core, feature)


SUBCOMMANDS = {
    "worktrees": worktrees_command,
    "release": release_command,
    "suite": suite_command,
}
