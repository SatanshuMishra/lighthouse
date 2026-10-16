import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple

FINDINGS = "findings.json"
VERDICT = "verdict.json"
REPORT = "report.md"
PATH_KINDS = ("new", "neighbour")
PATH_STATUSES = ("passed", "failed", "unproven")
RUN_OUTCOMES = ("passed", "failed", None)
BUILD_RESULTS = ("ok", "blocked")

PASSED = "passed"
CONFIRMED_FAILURE = "confirmed failure"
PRE_EXISTING = "pre-existing"
FLAKY = "flaky"
UNPROVEN = "unproven"


class Refusal(Exception):
    pass


class Malformed(Refusal):
    def __init__(self, key: str, problem: str) -> None:
        super().__init__("{} in {}: {}".format(key, FINDINGS, problem))
        self.key = key


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Refusal(message)


def parser() -> Parser:
    arguments = Parser(prog="lighthouse verdict", add_help=False)
    arguments.add_argument("--results", required=True)
    return arguments


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        results = os.path.realpath(options.results)
        findings = read_findings(results)
        judged = judge(findings)
        line = verdict_line(findings, judged)
        write_text(os.path.join(results, VERDICT), json.dumps(line) + "\n")
        write_text(os.path.join(results, REPORT), report(findings, judged, line))
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


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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


def check_spend(spend: Any) -> None:
    expect(is_count(required(spend, "tokens", "spend")), "spend.tokens", "must be a whole number")
    minutes = required(spend, "minutes", "spend")
    expect(is_number(minutes) and minutes >= 0, "spend.minutes", "must be a number")


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


def classify_trials(trials: Dict[str, Any], neighbour: bool) -> str:
    count = trials["count"]
    feature_passed = trials["feature_passed"]
    core_clean = not neighbour or trials["core_passed"] == count
    if feature_passed <= 1 and feature_passed < count and core_clean:
        return CONFIRMED_FAILURE
    if feature_passed == count:
        return PASSED
    return FLAKY


def judge(findings: Dict[str, Any]) -> Tuple[Tuple[Dict[str, Any], str], ...]:
    return tuple((path, classify(path)) for path in findings["paths"])


def named(judged: Tuple[Tuple[Dict[str, Any], str], ...], classification: str) -> List[str]:
    return [path["name"] for path, outcome in judged if outcome == classification]


def suite_ids(suite: Dict[str, Any], key: str) -> List[str]:
    return ["suite: {}".format(suite_test_id(entry)) for entry in suite[key]]


def verdict_of(findings: Dict[str, Any], judged: Tuple[Tuple[Dict[str, Any], str], ...]) -> str:
    if findings["suite"]["result"] == "blocked" or findings["build"]["result"] == "blocked":
        return "blocked"
    if findings["suite"]["failures"] or named(judged, CONFIRMED_FAILURE):
        return "failures"
    if all(outcome == UNPROVEN for path, outcome in judged if path["kind"] == "new"):
        return "unproven"
    return "green"


def verdict_line(findings: Dict[str, Any], judged: Tuple[Tuple[Dict[str, Any], str], ...]) -> Dict[str, Any]:
    suite = findings["suite"]
    return {
        "verdict": verdict_of(findings, judged),
        "failures": suite_ids(suite, "failures") + named(judged, CONFIRMED_FAILURE),
        "unproven": named(judged, UNPROVEN),
        "flaky": suite_ids(suite, "flaky") + named(judged, FLAKY),
        "tokens": findings["spend"]["tokens"],
        "minutes": findings["spend"]["minutes"],
        "pr": None,
    }


def write_text(path: str, text: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(path, error.strerror or error))


def bullets(lines: List[str]) -> List[str]:
    return ["- " + line for line in lines] if lines else ["None."]


def path_line(path: Dict[str, Any], outcome: str) -> str:
    evidence = ", ".join(path["evidence"]) if path["evidence"] else "none"
    return "{} ({}): {}; status {}, retry {}, core {}{}; expected: {}; evidence: {}".format(
        path["name"],
        path["surface"],
        outcome,
        path["status"],
        path["retry"] or "none",
        path["core"] or "none",
        trials_text(path["trials"]),
        path["expected"],
        evidence,
    )


def trials_text(trials: Optional[Dict[str, Any]]) -> str:
    if trials is None:
        return ""
    core_passed = "none" if trials["core_passed"] is None else trials["core_passed"]
    return "; trials {}, FEATURE passed {}, core passed {}".format(
        trials["count"], trials["feature_passed"], core_passed
    )


def lines_of_kind(judged: Tuple[Tuple[Dict[str, Any], str], ...], kind: str) -> List[str]:
    return [path_line(path, outcome) for path, outcome in judged if path["kind"] == kind]


def lines_classified(judged: Tuple[Tuple[Dict[str, Any], str], ...], classification: str) -> List[str]:
    return [path_line(path, outcome) for path, outcome in judged if outcome == classification]


def section(title: str, lines: List[str]) -> List[str]:
    return ["## " + title, ""] + lines + [""]


def report(
    findings: Dict[str, Any],
    judged: Tuple[Tuple[Dict[str, Any], str], ...],
    line: Dict[str, Any],
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
        + section("Unproven", bullets(lines_classified(judged, UNPROVEN)))
        + section("Flaky", bullets(suite_ids(suite, "flaky") + lines_classified(judged, FLAKY)))
        + section("Pre-existing", bullets(suite_ids(suite, "pre_existing") + lines_classified(judged, PRE_EXISTING)))
        + section(
            "Spend",
            ["Tokens: {}".format(findings["spend"]["tokens"]), "Minutes: {}".format(findings["spend"]["minutes"])],
        )
    )
    return "\n".join(lines).rstrip("\n") + "\n"
