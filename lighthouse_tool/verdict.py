import json
import os
from typing import Any, Dict, List, Optional, Tuple
from lighthouse_tool.records import PRIVATE_FILE, append_json_line, is_number, utc_now
from lighthouse_tool.repo import Parser, Refusal, ensure_state_dir, repository_folder, require_root

FINDINGS = "findings.json"
RETEST = "retest.json"
CARRIED_FOLDER = "previous"
VERDICT = "verdict.json"
REPORT = "report.md"
LEDGER = "runs.jsonl"
SPEND = "spend.json"
SUITE = "suite.json"
COMMITS = "commits.json"
BUILDS = ("core", "feature")
SUITE_PHASES = ("prepare_minutes", "suite_minutes", "rerun_minutes")
PATH_KINDS = ("new", "neighbour")
PATH_STATUSES = ("passed", "failed", "unproven")
RUN_OUTCOMES = ("passed", "failed", None)
BUILD_RESULTS = ("ok", "blocked")
CHECK_KINDS = ("suite", "direct", "drive")
SUITE_CHECK = "suite"

PASSED = "passed"
CONFIRMED_FAILURE = "confirmed failure"
PRE_EXISTING = "pre-existing"
FLAKY = "flaky"
UNPROVEN = "unproven"


class Malformed(Refusal):
    def __init__(self, key: str, problem: str, source: str = FINDINGS) -> None:
        super().__init__("{} in {}: {}".format(key, source, problem))
        self.key = key


def parser() -> Parser:
    arguments = Parser(prog="lighthouse verdict", add_help=False)
    arguments.add_argument("--results")
    arguments.add_argument("--blocked")
    arguments.add_argument("--repo")
    return arguments


def blocked_line(reason: str) -> Tuple[int, Optional[str], Optional[str]]:
    if not reason.strip():
        raise Refusal("--blocked needs the reason the run stopped")
    line = {"verdict": "blocked", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "pr": None}
    return 0, json.dumps(line), "lighthouse verdict: blocked: {}".format(reason.strip())


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        if options.results is None and options.blocked is None:
            raise Refusal("give --results, or --blocked with the reason the run stopped")
        root = require_root(options.repo) if options.repo is not None else None
        if options.blocked is not None:
            outcome = blocked_line(options.blocked)
            if root is not None:
                run_id = os.path.realpath(options.results) if options.results is not None else None
                append_ledger(root, blocked_record(root, options.blocked.strip(), run_id))
            return outcome
        results = os.path.realpath(options.results)
        findings = read_findings(results)
        plan = read_plan(results)
        carried = [] if plan is None else plan["carried_paths"]
        check_checks(findings, carried)
        skipped = skipped_retests(None if plan is None else plan["retest"], findings, results)
        judged = judge(findings, carried, recorded_test_ids(results))
        line = verdict_line(findings, judged, skipped)
        write_text(os.path.join(results, VERDICT), json.dumps(line) + "\n")
        write_text(os.path.join(results, REPORT), report(findings, judged, line, skipped))
        if root is not None:
            append_ledger(root, run_record(root, results, findings, line))
    except Malformed as malformed:
        return (
            2,
            json.dumps({"error": "findings do not match their schema", "key": malformed.key}),
            "lighthouse verdict: {}".format(malformed),
        )
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse verdict: {}".format(refusal)
    return 0, json.dumps(line), "lighthouse verdict: {}; report at {}".format(
        line["verdict"], os.path.join(results, REPORT)
    )


def read_findings(results: str) -> Dict[str, Any]:
    path = os.path.join(results, FINDINGS)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise Malformed(FINDINGS, "cannot be read: {}".format(error.strerror or error))
    try:
        findings = json.loads(text)
    except ValueError:
        raise Malformed(FINDINGS, "is not JSON")
    return checked_findings(findings, results)


def read_plan(results: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(results, RETEST)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise Malformed(RETEST, "cannot be read: {}".format(error.strerror or error), RETEST)
    try:
        plan = json.loads(text)
    except ValueError:
        raise Malformed(RETEST, "is not JSON", RETEST)
    return checked_plan(plan)


def checked_plan(plan: Any) -> Dict[str, Any]:
    names = plan.get("retest") if isinstance(plan, dict) else None
    if not (isinstance(names, list) and all(isinstance(name, str) for name in names)):
        raise Malformed(RETEST, "must be a JSON object with a retest list of path names", RETEST)
    carried = plan.get("carried_paths", [])
    if not (isinstance(carried, list) and all(isinstance(path, dict) for path in carried)):
        raise Malformed("carried_paths", "must be a list of path objects", RETEST)
    return {
        "retest": [name for index, name in enumerate(names) if name not in names[:index]],
        "carried_paths": carried,
    }


def lies_in(folder: os.stat_result, located: str) -> bool:
    parent = os.path.dirname(located)
    return parent != located and (os.path.samestat(folder, os.stat(parent)) or lies_in(folder, parent))


def is_fresh(item: str, results: str, carried: Optional[os.stat_result]) -> bool:
    located = os.path.realpath(os.path.join(results, item))
    return os.path.isfile(located) and not (carried is not None and lies_in(carried, located))


def carried_folder(results: str) -> Optional[os.stat_result]:
    folder = os.path.join(results, CARRIED_FOLDER)
    return os.stat(folder) if os.path.isdir(folder) else None


def driven_again(path: Dict[str, Any], results: str, carried: Optional[os.stat_result]) -> bool:
    return any(is_fresh(item, results, carried) for item in path["evidence"])


def skipped_retests(plan: Optional[List[str]], findings: Dict[str, Any], results: str) -> List[str]:
    if plan is None:
        return []
    carried = carried_folder(results)
    driven = {path["name"] for path in findings["paths"] if driven_again(path, results, carried)}
    return [name for name in plan if name not in driven]


def is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def required(record: Any, key: str, where: str) -> Any:
    if not isinstance(record, dict):
        raise Malformed(where, "must be an object")
    if key not in record:
        raise Malformed(qualified(where, key), "is missing")
    return record[key]


def qualified(where: str, key: str) -> str:
    return key if where == FINDINGS else "{}.{}".format(where, key)


def expect(condition: bool, key: str, problem: str) -> None:
    if not condition:
        raise Malformed(key, problem)


def checked_findings(findings: Any, results: str) -> Dict[str, Any]:
    expect(isinstance(findings, dict), FINDINGS, "must be a JSON object")
    expect(required(findings, "version", FINDINGS) == 1, "version", "must be 1")
    check_suite(required(findings, "suite", FINDINGS))
    check_build(required(findings, "build", FINDINGS))
    paths = required(findings, "paths", FINDINGS)
    expect(isinstance(paths, list), "paths", "must be a list")
    for index, path in enumerate(paths):
        check_path(path, "paths[{}]".format(index), results)
    check_spend(required(findings, "spend", FINDINGS))
    return findings


def check_suite(suite: Any) -> None:
    result = required(suite, "result", "suite")
    expect(isinstance(result, str), "suite.result", "must be a string")
    reason = required(suite, "reason", "suite")
    expect(reason is None or isinstance(reason, str), "suite.reason", "must be a string or null")
    for key in ("failures", "pre_existing", "flaky"):
        entries = required(suite, key, "suite")
        expect(isinstance(entries, list), "suite." + key, "must be a list")
        for index, entry in enumerate(entries):
            expect(
                suite_test_id(entry) is not None,
                "suite.{}[{}]".format(key, index),
                "must be a test id or an object with a string id",
            )


def suite_test_id(entry: Any) -> Optional[str]:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("id"), str):
        return entry["id"]
    return None


def check_build(build: Any) -> None:
    expect(required(build, "result", "build") in BUILD_RESULTS, "build.result", "must be ok or blocked")
    reason = required(build, "reason", "build")
    expect(reason is None or isinstance(reason, str), "build.reason", "must be a string or null")


def check_path(path: Any, where: str, results: str) -> None:
    for key in ("name", "surface", "expected"):
        expect(isinstance(required(path, key, where), str), "{}.{}".format(where, key), "must be a string")
    expect(required(path, "kind", where) in PATH_KINDS, where + ".kind", "must be new or neighbour")
    expect(
        required(path, "status", where) in PATH_STATUSES,
        where + ".status",
        "must be passed, failed or unproven",
    )
    for key in ("retry", "core"):
        expect(
            required(path, key, where) in RUN_OUTCOMES,
            "{}.{}".format(where, key),
            "must be passed, failed or null",
        )
    evidence = required(path, "evidence", where)
    expect(isinstance(evidence, list), where + ".evidence", "must be a list")
    for index, item in enumerate(evidence):
        expect(
            isinstance(item, str) and is_under(results, item),
            "{}.evidence[{}]".format(where, index),
            "must be a path under the results folder",
        )
    check_trials(required(path, "trials", where), where + ".trials")


def is_under(results: str, item: str) -> bool:
    if not item:
        return False
    located = os.path.realpath(os.path.join(results, item))
    return os.path.commonpath([results, located]) == results


def check_trials(trials: Any, where: str) -> None:
    if trials is None:
        return
    count = required(trials, "count", where)
    expect(is_count(count) and count >= 1, where + ".count", "must be a whole number of at least 1")
    feature_passed = required(trials, "feature_passed", where)
    expect(
        is_count(feature_passed) and feature_passed <= count,
        where + ".feature_passed",
        "must be a whole number no larger than count",
    )
    core_passed = required(trials, "core_passed", where)
    expect(
        core_passed is None or (is_count(core_passed) and core_passed <= count),
        where + ".core_passed",
        "must be null or a whole number no larger than count",
    )


def check_checks(findings: Dict[str, Any], carried: List[Dict[str, Any]]) -> None:
    for index, path in enumerate(findings["paths"]):
        if path not in carried:
            check_check(required(path, "check", "paths[{}]".format(index)), "paths[{}].check".format(index))


def check_check(check: Any, where: str) -> None:
    kind = required(check, "kind", where)
    expect(kind in CHECK_KINDS, where + ".kind", "must be suite, direct or drive")
    why = required(check, "why", where)
    expect(isinstance(why, str) and bool(why.strip()), where + ".why", "must be a non-empty string")
    if kind == SUITE_CHECK:
        tests = required(check, "tests", where)
        expect(
            isinstance(tests, list) and bool(tests) and all(isinstance(test, str) and test for test in tests),
            where + ".tests",
            "must name at least one test id for a suite check",
        )
    else:
        expect(
            check.get("tests") in (None, []),
            where + ".tests",
            "must be absent or empty for a direct or drive check",
        )


def check_spend(spend: Any) -> None:
    expect(is_count(required(spend, "tokens", "spend")), "spend.tokens", "must be a whole number")
    minutes = required(spend, "minutes", "spend")
    expect(is_number(minutes) and minutes >= 0, "spend.minutes", "must be a number")
    dollars = spend.get("dollars")
    expect(dollars is None or (is_number(dollars) and dollars >= 0), "spend.dollars", "must be a number or null")


def classify(path: Dict[str, Any]) -> str:
    neighbour = path["kind"] == "neighbour"
    trials = path["trials"]
    if path["status"] == "unproven":
        return UNPROVEN
    if trials is not None:
        return classify_trials(trials, neighbour)
    if path["status"] == "passed":
        return PASSED
    failed_twice = path["status"] == "failed" and path["retry"] == "failed"
    if failed_twice and (not neighbour or path["core"] == "passed"):
        return CONFIRMED_FAILURE
    if failed_twice and neighbour and path["core"] == "failed":
        return PRE_EXISTING
    if path["status"] == "failed" and path["retry"] == "passed":
        return FLAKY
    return UNPROVEN


def failing(passed: int, count: int) -> bool:
    return passed <= 1 and passed < count


def classify_trials(trials: Dict[str, Any], neighbour: bool) -> str:
    count = trials["count"]
    feature_passed = trials["feature_passed"]
    core_passed = trials["core_passed"]
    if feature_passed == count:
        return PASSED
    if not failing(feature_passed, count):
        return FLAKY
    if not neighbour or core_passed == count:
        return CONFIRMED_FAILURE
    if core_passed is None:
        return UNPROVEN
    if failing(core_passed, count):
        return PRE_EXISTING
    return FLAKY


def passed_ids(suite: Any, build: str) -> Optional[List[str]]:
    summary = suite.get(build) if isinstance(suite, dict) else None
    tests = summary.get("tests") if isinstance(summary, dict) else None
    passed = tests.get("passed") if isinstance(tests, dict) else None
    if isinstance(passed, list) and all(isinstance(test, str) for test in passed):
        return passed
    return None


def recorded_test_ids(results: str) -> Dict[str, Optional[List[str]]]:
    suite = optional_json(os.path.join(results, SUITE))
    return {build: passed_ids(suite, build) for build in BUILDS}


def missing_from(build: str, label: str, tests: List[str], recorded: Dict[str, Optional[List[str]]]) -> Optional[str]:
    passed = recorded[build]
    if passed is None:
        return "suite check: {} records no test ids for {}".format(SUITE, label)
    missing = [test for test in tests if test not in passed]
    if missing:
        return "suite check: {} did not pass on {}'s first run".format(", ".join(missing), label)
    return None


def suite_check_problem(path: Dict[str, Any], recorded: Dict[str, Optional[List[str]]]) -> Optional[str]:
    check = path.get("check")
    if not isinstance(check, dict) or check.get("kind") != SUITE_CHECK:
        return None
    tests = check["tests"]
    feature_problem = missing_from("feature", "FEATURE", tests, recorded)
    if feature_problem is not None or path["kind"] != "neighbour":
        return feature_problem
    return missing_from("core", "core", tests, recorded)


def judged_path(
    path: Dict[str, Any], carried: List[Dict[str, Any]], recorded: Dict[str, Optional[List[str]]]
) -> Tuple[Dict[str, Any], str, Optional[str]]:
    outcome = classify(path)
    problem = None if path in carried else suite_check_problem(path, recorded)
    if problem is None or outcome == CONFIRMED_FAILURE:
        return path, outcome, None
    return path, UNPROVEN, problem


def judge(
    findings: Dict[str, Any], carried: List[Dict[str, Any]], recorded: Dict[str, Optional[List[str]]]
) -> Tuple[Tuple[Dict[str, Any], str, Optional[str]], ...]:
    return tuple(judged_path(path, carried, recorded) for path in findings["paths"])


def named(judged: Tuple[Tuple[Dict[str, Any], str, Optional[str]], ...], classification: str) -> List[str]:
    return [path["name"] for path, outcome, _ in judged if outcome == classification]


def suite_ids(suite: Dict[str, Any], key: str) -> List[str]:
    return ["suite: {}".format(suite_test_id(entry)) for entry in suite[key]]


def verdict_of(findings: Dict[str, Any], judged: Tuple[Tuple[Dict[str, Any], str, Optional[str]], ...]) -> str:
    if findings["suite"]["result"] == "blocked" or findings["build"]["result"] == "blocked":
        return "blocked"
    if findings["suite"]["failures"] or named(judged, CONFIRMED_FAILURE):
        return "failures"
    if all(outcome == UNPROVEN for path, outcome, _ in judged if path["kind"] == "new"):
        return "unproven"
    return "green"


def held_to_plan(verdict: str, skipped: List[str]) -> str:
    return UNPROVEN if skipped and verdict == "green" else verdict


def unproven_names(judged: Tuple[Tuple[Dict[str, Any], str, Optional[str]], ...], skipped: List[str]) -> List[str]:
    judged_unproven = named(judged, UNPROVEN)
    return judged_unproven + [name for name in skipped if name not in judged_unproven]


def verdict_line(
    findings: Dict[str, Any],
    judged: Tuple[Tuple[Dict[str, Any], str, Optional[str]], ...],
    skipped: List[str],
) -> Dict[str, Any]:
    suite = findings["suite"]
    return {
        "verdict": held_to_plan(verdict_of(findings, judged), skipped),
        "failures": suite_ids(suite, "failures") + named(judged, CONFIRMED_FAILURE),
        "unproven": unproven_names(judged, skipped),
        "flaky": suite_ids(suite, "flaky") + named(judged, FLAKY),
        "tokens": findings["spend"]["tokens"],
        "minutes": findings["spend"]["minutes"],
        "dollars": findings["spend"].get("dollars"),
        "pr": None,
    }


def write_text(path: str, text: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(path, error.strerror or error))


def bullets(lines: List[str], empty: str = "None.") -> List[str]:
    return ["- " + line for line in lines] if lines else [empty]


def path_line(path: Dict[str, Any], outcome: str, problem: Optional[str]) -> str:
    evidence = ", ".join(path["evidence"]) if path["evidence"] else "none"
    return "{} ({}): {}{}; status {}, retry {}, core {}{}; {}; expected: {}; evidence: {}".format(
        path["name"],
        path["surface"],
        outcome,
        " ({})".format(problem) if problem else "",
        path["status"],
        path["retry"] or "none",
        path["core"] or "none",
        trials_text(path["trials"]),
        check_text(path.get("check")),
        path["expected"],
        evidence,
    )


def check_text(check: Any) -> str:
    if not isinstance(check, dict):
        return "check none"
    tests = check.get("tests") or []
    named_tests = " ({})".format(", ".join(tests)) if tests else ""
    return "check {}{}: {}".format(check.get("kind"), named_tests, check.get("why"))


def trials_text(trials: Optional[Dict[str, Any]]) -> str:
    if trials is None:
        return ""
    core_passed = "none" if trials["core_passed"] is None else trials["core_passed"]
    return "; trials {}, FEATURE passed {}, core passed {}".format(
        trials["count"], trials["feature_passed"], core_passed
    )


def lines_of_kind(judged: Tuple[Tuple[Dict[str, Any], str, Optional[str]], ...], kind: str) -> List[str]:
    return [path_line(path, outcome, problem) for path, outcome, problem in judged if path["kind"] == kind]


def lines_classified(judged: Tuple[Tuple[Dict[str, Any], str, Optional[str]], ...], classification: str) -> List[str]:
    return [path_line(path, outcome, problem) for path, outcome, problem in judged if outcome == classification]


def skipped_lines(skipped: List[str]) -> List[str]:
    return ["{}: planned for retest but not driven again".format(name) for name in skipped]


def section(title: str, lines: List[str]) -> List[str]:
    return ["## " + title, ""] + lines + [""]


def report(
    findings: Dict[str, Any],
    judged: Tuple[Tuple[Dict[str, Any], str, Optional[str]], ...],
    line: Dict[str, Any],
    skipped: List[str],
) -> str:
    suite = findings["suite"]
    build = findings["build"]
    suite_lines = [
        "Result: {}{}".format(suite["result"], "; " + suite["reason"] if suite["reason"] else ""),
        "FEATURE build for product testing: {}{}".format(
            build["result"], "; " + build["reason"] if build["reason"] else ""
        ),
        "",
        "Failures:",
    ] + bullets(suite_ids(suite, "failures")) + ["", "Flaky:"] + bullets(suite_ids(suite, "flaky")) + [
        "",
        "Pre-existing:",
    ] + bullets(suite_ids(suite, "pre_existing"))
    verdict_lines = [
        "Verdict: {}".format(line["verdict"]),
        "",
        "Failures:",
    ] + bullets(line["failures"])
    lines = (
        ["# lighthouse report", ""]
        + section("Verdict", verdict_lines)
        + section("Suite", suite_lines)
        + section("New behaviour", bullets(lines_of_kind(judged, "new")))
        + section("Neighbours", bullets(lines_of_kind(judged, "neighbour")))
        + section("Unproven", bullets(lines_classified(judged, UNPROVEN) + skipped_lines(skipped)))
        + section("Flaky", bullets(suite_ids(suite, "flaky") + lines_classified(judged, FLAKY)))
        + section("Pre-existing", bullets(suite_ids(suite, "pre_existing") + lines_classified(judged, PRE_EXISTING)))
        + section(
            "Spend",
            [
                "Tokens: {}".format(findings["spend"]["tokens"]),
                "Minutes: {}".format(findings["spend"]["minutes"]),
                "Dollars: {}".format("unknown" if line["dollars"] is None else line["dollars"]),
            ],
        )
    )
    return "\n".join(lines).rstrip("\n") + "\n"


def optional_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def recorded_commits(results: str) -> Optional[Dict[str, Any]]:
    commits = optional_json(os.path.join(results, COMMITS))
    if not isinstance(commits, dict):
        return None
    return {build: commits.get(build) if isinstance(commits.get(build), str) else None for build in BUILDS}


def phase_minutes(build: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(build, dict):
        return None
    return {phase: build[phase] for phase in SUITE_PHASES if phase in build}


def recorded_suite(results: str) -> Optional[Dict[str, Any]]:
    suite = optional_json(os.path.join(results, SUITE))
    if not isinstance(suite, dict):
        return None
    return {build: phase_minutes(suite.get(build)) for build in BUILDS}


def recorded_spend(results: str, findings: Dict[str, Any]) -> Dict[str, Any]:
    spend = optional_json(os.path.join(results, SPEND))
    if isinstance(spend, dict):
        return spend
    claimed = findings["spend"]
    return {"tokens": claimed["tokens"], "minutes": claimed["minutes"], "dollars": claimed.get("dollars")}


def ledger_path(path: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": path["name"], "kind": path["kind"], "status": path["status"], "check": path.get("check")}


def run_record(root: str, results: str, findings: Dict[str, Any], line: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run": results,
        "kind": "verdict",
        "time": utc_now(),
        "repo": repository_folder(root),
        "commits": recorded_commits(results),
        "verdict": line["verdict"],
        "reason": None,
        "spend": recorded_spend(results, findings),
        "suite": recorded_suite(results),
        "paths": [ledger_path(path) for path in findings["paths"]],
    }


def blocked_record(root: str, reason: str, run_id: Optional[str]) -> Dict[str, Any]:
    return {
        "run": run_id,
        "kind": "verdict",
        "time": utc_now(),
        "repo": repository_folder(root),
        "commits": None,
        "verdict": "blocked",
        "reason": reason,
        "spend": None,
        "suite": None,
        "paths": [],
    }


def append_ledger(root: str, record: Dict[str, Any]) -> None:
    folder = ensure_state_dir(root)
    if folder is None:
        raise Refusal("cannot find the state folder of {}".format(root))
    path = os.path.join(folder, LEDGER)
    try:
        append_json_line(path, record, PRIVATE_FILE)
    except OSError as error:
        raise Refusal("cannot append to {}: {}".format(path, error.strerror or error))
