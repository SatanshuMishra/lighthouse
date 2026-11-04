import json
import os
import re
from typing import Any, Dict, List, NamedTuple, Optional, Tuple
from lighthouse_tool import handoff, record_lines
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
H13 = "h13-lighthouse-verdict-line"
H14 = "h14-lighthouse-findings"
FINDINGS_PRODUCER = "the lighthouse:test child session"
PLAN_PRODUCER = "lighthouse execute"
RETEST_PRODUCER = "lighthouse retest"
ROOT_POINTER = "#"
ERROR_POINTER = re.compile(r"^(#.*?) [A-Za-z$]+: ")
BUILDS = ("core", "feature")
FEATURE = "feature"
SUITE_PHASES = ("prepare_minutes", "suite_minutes", "rerun_minutes")
SUITE_FIELDS = ("result", "reason", "failures", "pre_existing", "flaky")
PATH_KINDS = ("new", "neighbour")
PATH_STATUSES = ("passed", "failed", "unproven")
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
VERDICTS = ("green", "failures", "blocked", "unproven")

JudgedPath = Tuple[Dict[str, Any], str, Optional[str]]


class Malformed(Refusal):
    def __init__(self, key: str, message: str) -> None:
        super().__init__(message)
        self.key = key


def broken_rule(source: str, producer: str, pointer: str, problem: str) -> Malformed:
    return Malformed(pointer, "{} from {}: {} {}".format(source, producer, pointer, problem))


def findings_rule(pointer: str, problem: str) -> Malformed:
    return broken_rule(FINDINGS, FINDINGS_PRODUCER, pointer, problem)


def pointer_of(error: str) -> str:
    found = ERROR_POINTER.match(error)
    return found.group(1) if found else ROOT_POINTER


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
    line = checked_line(
        "the blocked line",
        {
            "verdict": "blocked",
            "failures": [],
            "unproven": [],
            "flaky": [],
            "tokens": 0,
            "minutes": 0,
            "pr": None,
            "reason": reason.strip(),
        },
    )
    return 0, json.dumps(line), "lighthouse verdict: blocked: {}".format(reason.strip())


def checked_line(target: str, line: Dict[str, Any]) -> Dict[str, Any]:
    return handoff.check_before_writing("{} {}".format(target, json.dumps(line)), H13, line)


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        if options.results is None and options.blocked is None:
            raise Refusal("give --results, or --blocked with the reason the run stopped")
        if options.blocked is not None:
            return blocked_line(options.blocked)
        results = os.path.realpath(options.results)
        judgement = judged_run(results)
        line = checked_line("{} with the verdict line".format(VERDICT), verdict_line(judgement))
        write_text(os.path.join(results, VERDICT), json.dumps(line) + "\n")
        write_text(os.path.join(results, REPORT), report(judgement, line))
    except Malformed as malformed:
        return 2, json.dumps({"error": str(malformed), "key": malformed.key}), "lighthouse verdict: {}".format(malformed)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse verdict: {}".format(refusal)
    return 0, json.dumps(line), "lighthouse verdict: {}; report at {}".format(
        line["verdict"], os.path.join(results, REPORT)
    )


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


def read_json_file(path: str, source: str, producer: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise broken_rule(source, producer, ROOT_POINTER, "cannot be read: {}".format(error.strerror or error))
    try:
        return json.loads(text)
    except ValueError:
        raise broken_rule(source, producer, ROOT_POINTER, "is not JSON")


def read_findings(results: str) -> Dict[str, Any]:
    found = read_json_file(os.path.join(results, FINDINGS), FINDINGS, FINDINGS_PRODUCER)
    return checked_findings(through_h14(found), results)


def through_h14(findings: Any) -> Dict[str, Any]:
    try:
        return handoff.read_through(FINDINGS_PRODUCER, FINDINGS, H14, findings)
    except handoff.FormatRefusal as refusal:
        raise Malformed(pointer_of(refusal.errors[0]), str(refusal))


def read_retest(results: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(results, RETEST)
    if not os.path.exists(path):
        return None
    return checked_retest(read_json_file(path, RETEST, RETEST_PRODUCER))


def checked_retest(plan: Any) -> Dict[str, Any]:
    names = plan.get("retest") if isinstance(plan, dict) else None
    if not (isinstance(names, list) and all(isinstance(name, str) for name in names)):
        raise broken_rule(RETEST, RETEST_PRODUCER, "#/retest", "must be a list of path names in a JSON object")
    carried = plan.get("carried_paths", [])
    if not (isinstance(carried, list) and all(isinstance(path, dict) for path in carried)):
        raise broken_rule(RETEST, RETEST_PRODUCER, "#/carried_paths", "must be a list of path objects")
    return {"retest": unique(names), "carried_paths": carried}


def unique(names: List[str]) -> List[str]:
    return [name for index, name in enumerate(names) if name not in names[:index]]


def read_execute_plan(results: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(results, PLAN)
    if not os.path.exists(path):
        return None
    return checked_execute_plan(read_json_file(path, PLAN, PLAN_PRODUCER))


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
        raise broken_rule(PLAN, PLAN_PRODUCER, "#/checks", "must be a list of checks with id, kind and trials in a JSON object")
    neighbours = plan.get("neighbours", [])
    if not (isinstance(neighbours, list) and all(isinstance(name, str) for name in neighbours)):
        raise broken_rule(PLAN, PLAN_PRODUCER, "#/neighbours", "must be a list of surface names")
    reach = plan.get("reach", {})
    if not (isinstance(reach, dict) and all(isinstance(reached, bool) for reached in reach.values())):
        raise broken_rule(PLAN, PLAN_PRODUCER, "#/reach", "must map surface names to true or false")
    refuse_repeated_checks([check["id"] for check in checks])
    return {"checks": checks, "neighbours": unique(neighbours), "reach": reach}


def refuse_repeated_checks(ids: List[str]) -> None:
    repeats = [index for index, check_id in enumerate(ids) if check_id in ids[:index]]
    if repeats:
        repeated = repeats[0]
        raise broken_rule(
            PLAN,
            PLAN_PRODUCER,
            "#/checks/{}/id".format(repeated),
            "repeats the check id {} of #/checks/{}/id; each planned check needs its own id".format(
                ids[repeated], ids.index(ids[repeated])
            ),
        )


def record_check_ids(results: str) -> List[str]:
    path = os.path.join(results, RECORD)
    if not os.path.exists(path):
        return []
    return [line["id"] for line in record_lines.lines_at(path)]


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
    found = handoff.schema_errors(K3_SCHEMA, result)
    if found:
        return None, "{}: fails {}: {}".format(where, handoff.schema_file(K3_SCHEMA), handoff.joined(found))
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
    if fails and passes:
        return FLAKY
    if fails and fails == len(statuses):
        return CONFIRMED_FAILURE
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
        and all(isinstance(entries, list) and all(isinstance(entry, str) for entry in entries) for entries in lists)
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


def checked_findings(findings: Dict[str, Any], results: str) -> Dict[str, Any]:
    for index, path in enumerate(findings["paths"]):
        check_evidence(path["evidence"], "#/paths/{}/evidence".format(index), results)
        if path["trials"] is not None:
            check_trials(path["trials"], "#/paths/{}/trials".format(index))
    return findings


def check_evidence(evidence: List[str], pointer: str, results: str) -> None:
    outside = [index for index, item in enumerate(evidence) if not is_under(results, item)]
    if outside:
        raise findings_rule("{}/{}".format(pointer, outside[0]), "must be a path under the results folder")


def is_under(results: str, item: str) -> bool:
    if not item:
        return False
    located = os.path.realpath(os.path.join(results, item))
    return os.path.commonpath([results, located]) == results


def check_trials(trials: Dict[str, Any], pointer: str) -> None:
    count = trials["count"]
    if trials["feature_passed"] > count:
        raise findings_rule(pointer + "/feature_passed", "must be no larger than count")
    if trials["core_passed"] is not None and trials["core_passed"] > count:
        raise findings_rule(pointer + "/core_passed", "must be null or no larger than count")


def check_checks(findings: Dict[str, Any], carried: List[Dict[str, Any]]) -> None:
    unchecked = [
        index for index, path in enumerate(findings["paths"]) if path not in carried and "check" not in path
    ]
    if unchecked:
        raise findings_rule(
            "#/paths/{}/check".format(unchecked[0]), "is missing; every path driven this run names its check"
        )


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
    return ["suite: {}".format(entry) for entry in suite[key]]


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
