import json
import os
from typing import Any, Dict, List, NamedTuple, Optional, Tuple
from lighthouse_tool import contract
from lighthouse_tool.records import is_number
from lighthouse_tool.repo import Parser, Refusal
from lighthouse_tool.results import CHECKS, PLAN, RECORD

FINDINGS = "findings.json"
RETEST = "retest.json"
CARRIED_FOLDER = "previous"
VERDICT = "verdict.json"
REPORT = "report.md"
SUITE = "suite.json"
COMMITS = "commits.json"
PROFILE = "profile.json"
K3_SCHEMA = "k3-check-result.schema.json"
BUILDS = ("core", "feature")
FEATURE = "feature"
SUITE_PHASES = ("prepare_minutes", "suite_minutes", "rerun_minutes")
SUITE_FIELDS = ("result", "reason", "failures", "pre_existing", "flaky")
PATH_KINDS = ("new", "neighbour")
PATH_STATUSES = ("passed", "failed", "unproven")
RUN_OUTCOMES = ("passed", "failed", None)
BUILD_RESULTS = ("ok", "blocked")
CHECK_KINDS = ("suite", "direct", "drive")
CHECK_RUN_KINDS = ("exact", "judged")
EXACT_RUNS = 1
SUITE_CHECK = "suite"
RESULT_PASS = "pass"
RESULT_FAIL = "fail"
RESULT_COULD_NOT_RUN = "could-not-run"
SUITE_MISSING = "suite.json is missing"
SUITE_INVALID = "suite.json is not a valid suite result"
SUITE_DIFFERS = "the findings suite differs from suite.json"

PASSED = "passed"
CONFIRMED_FAILURE = "confirmed failure"
PRE_EXISTING = "pre-existing"
FLAKY = "flaky"
UNPROVEN = "unproven"

JudgedPath = Tuple[Dict[str, Any], str, Optional[str]]


class Malformed(Refusal):
    def __init__(self, key: str, problem: str, source: str = FINDINGS) -> None:
        super().__init__("{} in {}: {}".format(key, source, problem))
        self.key = key
        self.source = source


class JudgedCheck(NamedTuple):
    check_id: str
    kind: str
    required: int
    planned: bool
    outcome: str
    statuses: Tuple[str, ...]
    evidence: Tuple[str, ...]


class Suite(NamedTuple):
    summary: Dict[str, Any]
    problem: Optional[str]


class Judgement(NamedTuple):
    findings: Dict[str, Any]
    suite: Suite
    checks: Tuple[JudgedCheck, ...]
    paths: Tuple[JudgedPath, ...]
    ignored_paths: Tuple[str, ...]
    ignored_results: Tuple[str, ...]
    neighbours: Tuple[str, ...]
    skipped: Tuple[str, ...]


def parser() -> Parser:
    arguments = Parser(prog="lighthouse verdict", add_help=False)
    arguments.add_argument("--results")
    arguments.add_argument("--blocked")
    return arguments


def blocked_line(reason: str) -> Tuple[int, Optional[str], Optional[str]]:
    if not reason.strip():
        raise Refusal("--blocked needs the reason the run stopped")
    line = {
        "verdict": "blocked",
        "failures": [],
        "unproven": [],
        "flaky": [],
        "tokens": 0,
        "minutes": 0,
        "pr": None,
        "reason": reason.strip(),
    }
    return 0, json.dumps(line), "lighthouse verdict: blocked: {}".format(reason.strip())


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        if options.results is None and options.blocked is None:
            raise Refusal("give --results, or --blocked with the reason the run stopped")
        if options.blocked is not None:
            return blocked_line(options.blocked)
        results = os.path.realpath(options.results)
        judgement = judged_run(results)
        line = verdict_line(judgement)
        write_text(os.path.join(results, VERDICT), json.dumps(line) + "\n")
        write_text(os.path.join(results, REPORT), report(judgement, line))
    except Malformed as malformed:
        return (
            2,
            json.dumps({"error": schema_error(malformed.source), "key": malformed.key}),
            "lighthouse verdict: {}".format(malformed),
        )
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse verdict: {}".format(refusal)
    return 0, json.dumps(line), "lighthouse verdict: {}; report at {}".format(
        line["verdict"], os.path.join(results, REPORT)
    )


def schema_error(source: str) -> str:
    return "findings do not match their schema" if source == FINDINGS else "{} does not match its schema".format(source)


def judged_run(results: str) -> Judgement:
    findings = read_findings(results)
    retest_plan = read_retest(results)
    carried = [] if retest_plan is None else retest_plan["carried_paths"]
    check_checks(findings, carried)
    skipped = skipped_retests(None if retest_plan is None else retest_plan["retest"], findings, results)
    plan = read_execute_plan(results)
    found, ignored_results = read_check_results(results, feature_commit(results))
    checks = tuple(judge_check(expected, found, results) for expected in expected_checks(plan, record_check_ids(results)))
    check_ids = [check.check_id for check in checks if check.planned]
    judged_paths = [path for path in findings["paths"] if path["name"] not in check_ids]
    unreached = unreached_surfaces(plan, profile_availability(results))
    return Judgement(
        findings=findings,
        suite=read_suite(results, findings["suite"]),
        checks=checks,
        paths=judge(judged_paths, carried, recorded_test_ids(results), unreached, results),
        ignored_paths=tuple(path["name"] for path in findings["paths"] if path["name"] in check_ids),
        ignored_results=tuple(ignored_results),
        neighbours=tuple([] if plan is None else plan["neighbours"]),
        skipped=tuple(skipped),
    )


def read_json_file(path: str, source: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise Malformed(source, "cannot be read: {}".format(error.strerror or error), source)
    try:
        return json.loads(text)
    except ValueError:
        raise Malformed(source, "is not JSON", source)


def read_findings(results: str) -> Dict[str, Any]:
    return checked_findings(read_json_file(os.path.join(results, FINDINGS), FINDINGS), results)


def read_retest(results: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(results, RETEST)
    if not os.path.exists(path):
        return None
    return checked_retest(read_json_file(path, RETEST))


def checked_retest(plan: Any) -> Dict[str, Any]:
    names = plan.get("retest") if isinstance(plan, dict) else None
    if not (isinstance(names, list) and all(isinstance(name, str) for name in names)):
        raise Malformed(RETEST, "must be a JSON object with a retest list of path names", RETEST)
    carried = plan.get("carried_paths", [])
    if not (isinstance(carried, list) and all(isinstance(path, dict) for path in carried)):
        raise Malformed("carried_paths", "must be a list of path objects", RETEST)
    return {"retest": unique(names), "carried_paths": carried}


def unique(names: List[str]) -> List[str]:
    return [name for index, name in enumerate(names) if name not in names[:index]]


def read_execute_plan(results: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(results, PLAN)
    if not os.path.exists(path):
        return None
    return checked_execute_plan(read_json_file(path, PLAN))


def is_planned_check(check: Any) -> bool:
    return (
        isinstance(check, dict)
        and isinstance(check.get("id"), str)
        and check.get("kind") in CHECK_RUN_KINDS
        and is_count(check.get("trials"))
        and check["trials"] >= 1
    )


def checked_execute_plan(plan: Any) -> Dict[str, Any]:
    checks = plan.get("checks") if isinstance(plan, dict) else None
    if not (isinstance(checks, list) and all(is_planned_check(check) for check in checks)):
        raise Malformed(PLAN, "must be a JSON object with a checks list of id, kind and trials", PLAN)
    neighbours = plan.get("neighbours", [])
    if not (isinstance(neighbours, list) and all(isinstance(name, str) for name in neighbours)):
        raise Malformed("neighbours", "must be a list of surface names", PLAN)
    reach = plan.get("reach", {})
    if not (isinstance(reach, dict) and all(isinstance(reached, bool) for reached in reach.values())):
        raise Malformed("reach", "must map surface names to true or false", PLAN)
    ids = unique([check["id"] for check in checks])
    first = [next(check for check in checks if check["id"] == check_id) for check_id in ids]
    return {"checks": first, "neighbours": unique(neighbours), "reach": reach}


def record_check_ids(results: str) -> List[str]:
    path = os.path.join(results, RECORD)
    if not os.path.exists(path):
        return []
    record = read_json_file(path, RECORD)
    criteria = record.get("criteria", []) if isinstance(record, dict) else None
    if not isinstance(criteria, list):
        raise Malformed(RECORD, "must be a JSON object with a criteria list", RECORD)
    return unique(
        [
            line["id"]
            for criterion in criteria
            if isinstance(criterion, dict) and isinstance(criterion.get("acceptance"), list)
            for line in criterion["acceptance"]
            if isinstance(line, dict) and isinstance(line.get("id"), str)
        ]
    )


def expected_checks(plan: Optional[Dict[str, Any]], record_ids: List[str]) -> List[Dict[str, Any]]:
    planned = [] if plan is None else plan["checks"]
    planned_ids = [check["id"] for check in planned]
    return [
        {"id": check["id"], "kind": check["kind"], "required": required_runs(check), "planned": True}
        for check in planned
    ] + [
        {"id": check_id, "kind": "exact", "required": EXACT_RUNS, "planned": False}
        for check_id in record_ids
        if check_id not in planned_ids
    ]


def required_runs(check: Dict[str, Any]) -> int:
    return check["trials"] if check["kind"] == "judged" else EXACT_RUNS


def feature_commit(results: str) -> Optional[str]:
    commits = recorded_commits(results)
    return None if commits is None else commits[FEATURE]


def read_check_results(results: str, commit: Optional[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    path = os.path.join(results, CHECKS)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return [], []
    except OSError as error:
        return [], ["{} cannot be read: {}".format(CHECKS, error.strerror or error)]
    read = [
        result_line(line, number, commit)
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]
    return [result for result, _ in read if result is not None], [problem for _, problem in read if problem is not None]


def result_line(text: str, number: int, commit: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    where = "{} line {}".format(CHECKS, number)
    try:
        result = json.loads(text)
    except ValueError:
        return None, "{}: not JSON".format(where)
    found = contract.problems(result, K3_SCHEMA)
    if found:
        return None, "{}: fails the K3 schema: {}".format(where, "; ".join(found))
    if result["commit"] != commit:
        return None, "{}: {} is at commit {}, not the FEATURE commit {}".format(
            where, result["check_id"], result["commit"], commit or "(commits.json records none)"
        )
    return result, None


def counts(item: Any, results: str) -> bool:
    if not isinstance(item, str) or not is_under(results, item):
        return False
    located = os.path.realpath(os.path.join(results, item))
    return os.path.isfile(located) and os.path.getsize(located) > 0


def run_status(result: Dict[str, Any], results: str) -> str:
    status = result["status"]
    if status == RESULT_COULD_NOT_RUN:
        return status
    proven = bool(result["evidence"]) and all(counts(item, results) for item in result["evidence"])
    return status if proven else RESULT_COULD_NOT_RUN


def check_outcome(statuses: List[str], required_count: int) -> str:
    passes = statuses.count(RESULT_PASS)
    fails = statuses.count(RESULT_FAIL)
    if fails and not passes:
        return CONFIRMED_FAILURE
    if fails:
        return FLAKY
    if passes >= required_count and RESULT_COULD_NOT_RUN not in statuses:
        return PASSED
    return UNPROVEN


def judge_check(expected: Dict[str, Any], found: List[Dict[str, Any]], results: str) -> JudgedCheck:
    own = [result for result in found if expected["planned"] and result["check_id"] == expected["id"]]
    statuses = [run_status(result, results) for result in own]
    return JudgedCheck(
        check_id=expected["id"],
        kind=expected["kind"],
        required=expected["required"],
        planned=expected["planned"],
        outcome=check_outcome(statuses, expected["required"]),
        statuses=tuple(statuses),
        evidence=tuple(item for result in own for item in result["evidence"]),
    )


def profile_availability(results: str) -> Dict[str, bool]:
    profile = optional_json(os.path.join(results, PROFILE))
    surfaces = profile.get("surfaces") if isinstance(profile, dict) else None
    listed = surfaces if isinstance(surfaces, list) else []
    return {
        surface["name"]: surface.get("available") is not False
        for surface in listed
        if isinstance(surface, dict) and isinstance(surface.get("name"), str)
    }


def unreached_surfaces(plan: Optional[Dict[str, Any]], available: Dict[str, bool]) -> Dict[str, str]:
    reach = {} if plan is None else plan["reach"]
    unreached = {
        name: "surface {} did not answer its reach command this run".format(name)
        for name, reached in reach.items()
        if not reached
    }
    unavailable = {
        name: "surface {} is marked unavailable in {}".format(name, PROFILE)
        for name, is_available in available.items()
        if not is_available and name not in reach
    }
    return {**unavailable, **unreached}


def read_suite(results: str, copy: Dict[str, Any]) -> Suite:
    path = os.path.join(results, SUITE)
    copied = {field: copy[field] for field in SUITE_FIELDS}
    if not os.path.exists(path):
        return Suite(copied, None) if copy["result"] == "blocked" else Suite(empty_suite(), SUITE_MISSING)
    recorded = optional_json(path)
    if not is_suite(recorded):
        return Suite(empty_suite(), SUITE_INVALID)
    summary = {field: recorded[field] for field in SUITE_FIELDS}
    return Suite(summary, None if summary == copied else SUITE_DIFFERS)


def empty_suite() -> Dict[str, Any]:
    return {"result": None, "reason": None, "failures": [], "pre_existing": [], "flaky": []}


def is_suite(recorded: Any) -> bool:
    if not isinstance(recorded, dict) or not all(field in recorded for field in SUITE_FIELDS):
        return False
    lists = [recorded[key] for key in ("failures", "pre_existing", "flaky")]
    return (
        isinstance(recorded["result"], str)
        and (recorded["reason"] is None or isinstance(recorded["reason"], str))
        and all(isinstance(entries, list) and all(suite_test_id(entry) is not None for entry in entries) for entries in lists)
    )


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


def evidence_problem(evidence: List[str], results: str) -> Optional[str]:
    if not evidence:
        return "no evidence"
    uncounted = [item for item in evidence if not counts(item, results)]
    if uncounted:
        return "evidence {} is missing or empty".format(", ".join(uncounted))
    return None


def classify(path: Dict[str, Any], unreached: Dict[str, str], results: str) -> Tuple[str, Optional[str]]:
    if path["surface"] in unreached:
        return UNPROVEN, unreached[path["surface"]]
    if path["status"] == "unproven":
        return UNPROVEN, None
    problem = evidence_problem(path["evidence"], results)
    if problem is not None:
        return UNPROVEN, problem
    if path["kind"] == "neighbour":
        return classify_neighbour(path), None
    return classify_new(path), None


def classify_new(path: Dict[str, Any]) -> str:
    trials = path["trials"]
    if trials is not None:
        if trials["feature_passed"] == trials["count"]:
            return PASSED
        return CONFIRMED_FAILURE if trials["feature_passed"] == 0 else FLAKY
    if path["status"] == "passed":
        return PASSED
    return FLAKY if path["retry"] == "passed" else CONFIRMED_FAILURE


def classify_neighbour(path: Dict[str, Any]) -> str:
    if path["trials"] is not None:
        return classify_neighbour_trials(path["trials"])
    if path["status"] == "passed":
        return PASSED
    failed_twice = path["retry"] == "failed"
    if failed_twice and path["core"] == "passed":
        return CONFIRMED_FAILURE
    if failed_twice and path["core"] == "failed":
        return PRE_EXISTING
    if path["retry"] == "passed":
        return FLAKY
    return UNPROVEN


def failing(passed: int, count: int) -> bool:
    return passed <= 1 and passed < count


def classify_neighbour_trials(trials: Dict[str, Any]) -> str:
    count = trials["count"]
    feature_passed = trials["feature_passed"]
    core_passed = trials["core_passed"]
    if feature_passed == count:
        return PASSED
    if not failing(feature_passed, count):
        return FLAKY
    if core_passed == count:
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
    path: Dict[str, Any],
    carried: List[Dict[str, Any]],
    recorded: Dict[str, Optional[List[str]]],
    unreached: Dict[str, str],
    results: str,
) -> JudgedPath:
    outcome, classified_problem = classify(path, unreached, results)
    if classified_problem is not None:
        return path, outcome, classified_problem
    problem = None if path in carried else suite_check_problem(path, recorded)
    if problem is None or outcome == CONFIRMED_FAILURE:
        return path, outcome, None
    return path, UNPROVEN, problem


def judge(
    paths: List[Dict[str, Any]],
    carried: List[Dict[str, Any]],
    recorded: Dict[str, Optional[List[str]]],
    unreached: Dict[str, str],
    results: str,
) -> Tuple[JudgedPath, ...]:
    return tuple(judged_path(path, carried, recorded, unreached, results) for path in paths)


def named(judged: Tuple[JudgedPath, ...], classification: str, kinds: Tuple[str, ...] = PATH_KINDS) -> List[str]:
    return [path["name"] for path, outcome, _ in judged if outcome == classification and path["kind"] in kinds]


def checks_classified(checks: Tuple[JudgedCheck, ...], classification: str) -> List[str]:
    return [check.check_id for check in checks if check.outcome == classification]


def suite_ids(suite: Dict[str, Any], key: str) -> List[str]:
    return ["suite: {}".format(suite_test_id(entry)) for entry in suite[key]]


def unproven_neighbours(judgement: Judgement) -> List[str]:
    proven = {path["surface"] for path, outcome, _ in judgement.paths if path["kind"] == "neighbour" and outcome != UNPROVEN}
    return ["neighbour {}".format(surface) for surface in judgement.neighbours if surface not in proven]


def verdict_of(judgement: Judgement) -> str:
    suite = judgement.suite.summary
    if suite["result"] == "blocked" or judgement.findings["build"]["result"] == "blocked":
        return "blocked"
    checks = judgement.checks
    paths = judgement.paths
    if (
        suite["failures"]
        or checks_classified(checks, CONFIRMED_FAILURE)
        or named(paths, CONFIRMED_FAILURE)
        or checks_classified(checks, FLAKY)
        or named(paths, FLAKY, ("new",))
    ):
        return "failures"
    if (
        checks_classified(checks, UNPROVEN)
        or named(paths, UNPROVEN, ("new",))
        or unproven_neighbours(judgement)
        or judgement.suite.problem is not None
        or judgement.skipped
        or not (checks or [path for path, _, _ in paths if path["kind"] == "new"])
    ):
        return "unproven"
    return "green"


def unproven_names(judgement: Judgement) -> List[str]:
    listed = (
        checks_classified(judgement.checks, UNPROVEN)
        + named(judgement.paths, UNPROVEN)
        + unproven_neighbours(judgement)
        + ([] if judgement.suite.problem is None else ["suite: {}".format(judgement.suite.problem)])
    )
    return listed + [name for name in judgement.skipped if name not in listed]


def verdict_line(judgement: Judgement) -> Dict[str, Any]:
    suite = judgement.suite.summary
    spend = judgement.findings["spend"]
    return {
        "verdict": verdict_of(judgement),
        "failures": suite_ids(suite, "failures")
        + checks_classified(judgement.checks, CONFIRMED_FAILURE)
        + named(judgement.paths, CONFIRMED_FAILURE),
        "unproven": unproven_names(judgement),
        "flaky": suite_ids(suite, "flaky") + checks_classified(judgement.checks, FLAKY) + named(judgement.paths, FLAKY),
        "tokens": spend["tokens"],
        "minutes": spend["minutes"],
        "dollars": spend.get("dollars"),
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


def judged_check_line(check: JudgedCheck) -> str:
    evidence = ", ".join(check.evidence) if check.evidence else "none"
    unplanned = "" if check.planned else " (not in {}, so lighthouse execute did not run it)".format(PLAN)
    return "{} ({}): {}{}; runs {} of {} required ({} pass, {} fail, {} could-not-run); evidence: {}".format(
        check.check_id,
        check.kind,
        check.outcome,
        unplanned,
        len(check.statuses),
        check.required,
        check.statuses.count(RESULT_PASS),
        check.statuses.count(RESULT_FAIL),
        check.statuses.count(RESULT_COULD_NOT_RUN),
        evidence,
    )


def checks_lines(judgement: Judgement) -> List[str]:
    ignored_paths = [
        "{}: a model-written path named like a planned check was ignored".format(name) for name in judgement.ignored_paths
    ]
    ignored_results = ["ignored: {}".format(problem) for problem in judgement.ignored_results]
    return bullets([judged_check_line(check) for check in judgement.checks] + ignored_results + ignored_paths)


def lines_of_kind(judged: Tuple[JudgedPath, ...], kind: str) -> List[str]:
    return [path_line(path, outcome, problem) for path, outcome, problem in judged if path["kind"] == kind]


def lines_classified(judged: Tuple[JudgedPath, ...], classification: str) -> List[str]:
    return [path_line(path, outcome, problem) for path, outcome, problem in judged if outcome == classification]


def checks_of(checks: Tuple[JudgedCheck, ...], classification: str) -> List[str]:
    return [judged_check_line(check) for check in checks if check.outcome == classification]


def skipped_lines(skipped: Tuple[str, ...]) -> List[str]:
    return ["{}: planned for retest but not driven again".format(name) for name in skipped]


def section(title: str, lines: List[str]) -> List[str]:
    return ["## " + title, ""] + lines + [""]


def suite_report(judgement: Judgement) -> List[str]:
    suite = judgement.suite.summary
    build = judgement.findings["build"]
    problem = [] if judgement.suite.problem is None else ["Problem: {}".format(judgement.suite.problem)]
    return (
        [
            "Result: {}{}".format(suite["result"] or "none", "; " + suite["reason"] if suite["reason"] else ""),
            "FEATURE build for product testing: {}{}".format(
                build["result"], "; " + build["reason"] if build["reason"] else ""
            ),
        ]
        + problem
        + ["", "Failures:"]
        + bullets(suite_ids(suite, "failures"))
        + ["", "Flaky:"]
        + bullets(suite_ids(suite, "flaky"))
        + ["", "Pre-existing:"]
        + bullets(suite_ids(suite, "pre_existing"))
    )


def report(judgement: Judgement, line: Dict[str, Any]) -> str:
    suite = judgement.suite.summary
    paths = judgement.paths
    spend = judgement.findings["spend"]
    neighbour_gaps = ["{}: no neighbour path on it was proven".format(entry) for entry in unproven_neighbours(judgement)]
    suite_gap = [] if judgement.suite.problem is None else ["suite: {}".format(judgement.suite.problem)]
    verdict_lines = ["Verdict: {}".format(line["verdict"]), "", "Failures:"] + bullets(line["failures"])
    lines = (
        ["# lighthouse report", ""]
        + section("Verdict", verdict_lines)
        + section("Suite", suite_report(judgement))
        + section("Checks", checks_lines(judgement))
        + section("New behaviour", bullets(lines_of_kind(paths, "new")))
        + section("Neighbours", bullets(lines_of_kind(paths, "neighbour")))
        + section(
            "Unproven",
            bullets(
                checks_of(judgement.checks, UNPROVEN)
                + lines_classified(paths, UNPROVEN)
                + neighbour_gaps
                + suite_gap
                + skipped_lines(judgement.skipped)
            ),
        )
        + section(
            "Flaky",
            bullets(suite_ids(suite, "flaky") + checks_of(judgement.checks, FLAKY) + lines_classified(paths, FLAKY)),
        )
        + section("Pre-existing", bullets(suite_ids(suite, "pre_existing") + lines_classified(paths, PRE_EXISTING)))
        + section(
            "Spend",
            [
                "Tokens: {}".format(spend["tokens"]),
                "Minutes: {}".format(spend["minutes"]),
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
