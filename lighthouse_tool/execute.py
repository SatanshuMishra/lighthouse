import argparse
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool import contract, credentials, records, retest, suite
from lighthouse_tool.change import changed_files
from lighthouse_tool.repo import Parser, Refusal
from lighthouse_tool.results import CHECKS, PLAN, RECORD

Outcome = Tuple[int, Optional[str], Optional[str]]
K1_SCHEMA = "k1-acceptance.schema.json"
K3_SCHEMA = "k3-check-result.schema.json"
RUNNER = "lighthouse execute"
FEATURE = "feature"
CHECK_STEP = "check"
REACH_STEP = "reach"
CHECK_EVIDENCE = "evidence/checks"
REACH_EVIDENCE = "evidence/reach.log"
SPEC_SUFFIX = ".md"
RECORD_SUFFIX = ".record.json"
EXACT_RUNS = 1
STATUS_BY_EXIT = {0: "pass", 1: "fail"}
COULD_NOT_RUN = "could-not-run"


def parser() -> Parser:
    arguments = Parser(prog="lighthouse execute", add_help=False)
    arguments.add_argument("--results", required=True)
    arguments.add_argument("--record")
    arguments.add_argument("--spec")
    arguments.add_argument("--profile")
    return arguments


def run(argv: List[str]) -> Outcome:
    try:
        options = parser().parse_args(argv[1:])
        summary = execute_command(options)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse execute: {}".format(refusal)
    return 0, json.dumps(summary), None


def execute_command(options: argparse.Namespace) -> Dict[str, Any]:
    results = os.path.realpath(options.results)
    commits = read_commits(results)
    lines = acceptance_lines(chosen_record(results, options.record, options.spec))
    profile = chosen_profile(results, options.profile)
    worktree = os.path.join(results, FEATURE)
    hidden = suite.hidden_values(worktree, profile)
    checks_path = os.path.join(results, CHECKS)
    records.write_atomically(checks_path, "")
    runs = [run_line(line, results, worktree, commits[FEATURE], profile, hidden) for line in lines]
    surfaces = profile_surfaces(profile)
    changed = changed_files(worktree, commits["core"], commits[FEATURE])
    neighbours = [surface["name"] for surface in surfaces if retest.is_touched(surface, changed)]
    plan = {
        "checks": [{"id": line["id"], "kind": line["kind"], "trials": trials_of(line)} for line in lines],
        "neighbours": neighbours,
        "changed": changed,
        "reach": reached(surfaces, results, worktree, profile, hidden),
    }
    records.write_atomically(os.path.join(results, PLAN), json.dumps(plan, indent=2) + "\n")
    return {
        "checks": [{"id": line["id"], "runs": statuses} for line, statuses in zip(lines, runs)],
        "neighbours": neighbours,
    }


def read_commits(results: str) -> Dict[str, str]:
    path = os.path.join(results, suite.COMMITS)
    try:
        with open(path, encoding="utf-8") as handle:
            commits = json.load(handle)
    except (OSError, ValueError):
        raise Refusal("no readable {}; run lighthouse worktrees into {} first".format(path, results))
    if not isinstance(commits, dict) or not all(isinstance(commits.get(build), str) for build in suite.BUILDS):
        raise Refusal("{} must be an object holding core and feature commits".format(path))
    return {build: commits[build] for build in suite.BUILDS}


def record_beside(spec: Optional[str]) -> Optional[str]:
    if spec is None or not spec.endswith(SPEC_SUFFIX):
        return None
    path = spec[: -len(SPEC_SUFFIX)] + RECORD_SUFFIX
    return path if os.path.isfile(path) else None


def chosen_record(results: str, record: Optional[str], spec: Optional[str]) -> Optional[Dict[str, Any]]:
    in_results = os.path.join(results, RECORD)
    path = record or record_beside(spec) or (in_results if os.path.isfile(in_results) else None)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            found = json.load(handle)
    except (OSError, ValueError) as error:
        raise Refusal("record {} is unreadable: {}".format(path, error))
    if not isinstance(found, dict):
        raise Refusal("record {} is not a JSON object".format(path))
    return found


def acceptance_lines(record: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    criteria = [] if record is None else record.get("criteria", [])
    if not isinstance(criteria, list):
        raise Refusal("the record's criteria must be a list")
    placed = [
        ("criteria[{}].acceptance[{}]".format(number, index), line)
        for number, criterion in enumerate(criteria)
        for index, line in enumerate(criterion_acceptance(criterion, number))
    ]
    seen: List[str] = []
    for position, line in placed:
        named = line.get("id") if isinstance(line, dict) and isinstance(line.get("id"), str) else position
        found = contract.problems(line, K1_SCHEMA)
        if found:
            raise Refusal("acceptance line {} fails the K1 schema: {}".format(named, "; ".join(found)))
        if named in seen:
            raise Refusal("acceptance line {} repeats an id".format(named))
        seen.append(named)
    return [line for _, line in placed]


def criterion_acceptance(criterion: Any, number: int) -> List[Any]:
    acceptance = criterion.get("acceptance", []) if isinstance(criterion, dict) else []
    if not isinstance(acceptance, list):
        raise Refusal("criteria[{}].acceptance must be a list".format(number))
    return acceptance


def chosen_profile(results: str, path: Optional[str]) -> Dict[str, Any]:
    if path is not None:
        return readable_profile(path)
    candidates = [os.path.join(results, "profile.json"), os.path.join(results, FEATURE, ".lighthouse", "profile.json")]
    present = [candidate for candidate in candidates if os.path.isfile(candidate)]
    return readable_profile(present[0]) if present else {}


def readable_profile(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            profile = json.load(handle)
    except (OSError, ValueError) as error:
        raise Refusal("profile {} is unreadable: {}".format(path, error))
    if not isinstance(profile, dict):
        raise Refusal("profile {} is not a JSON object".format(path))
    return profile


def profile_surfaces(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    surfaces = profile.get("surfaces")
    listed = surfaces if isinstance(surfaces, list) else []
    return [surface for surface in listed if isinstance(surface, dict) and isinstance(surface.get("name"), str)]


def trials_of(line: Dict[str, Any]) -> int:
    return line["trials"] if line["kind"] == "judged" else EXACT_RUNS


def run_line(
    line: Dict[str, Any],
    results: str,
    worktree: str,
    commit: str,
    profile: Dict[str, Any],
    hidden: credentials.Secrets,
) -> List[str]:
    if line["kind"] == "judged":
        return [run_once(line, number, results, worktree, commit, profile, hidden) for number in range(1, line["trials"] + 1)]
    first = run_once(line, 1, results, worktree, commit, profile, hidden)
    return [first, run_once(line, 2, results, worktree, commit, profile, hidden)] if first == "fail" else [first]


def run_once(
    line: Dict[str, Any],
    number: int,
    results: str,
    worktree: str,
    commit: str,
    profile: Dict[str, Any],
    hidden: credentials.Secrets,
) -> str:
    evidence = "{}/{}-{}.log".format(CHECK_EVIDENCE, line["id"], number)
    log_path = os.path.join(results, evidence)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    open(log_path, "w", encoding="utf-8").close()
    started = time.monotonic()
    step = suite.run_step(CHECK_STEP, line["command"], worktree, FEATURE, log_path, profile, hidden)
    seconds = round(time.monotonic() - started, 3)
    suite.append_log(log_path, ended(step), hidden)
    status = STATUS_BY_EXIT.get(step.exit, COULD_NOT_RUN)
    result = {
        "check_id": line["id"],
        "commit": commit,
        "surface": line["surface"],
        "status": status,
        "evidence": [evidence],
        "seconds": seconds,
        "runner": RUNNER,
    }
    found = contract.problems(result, K3_SCHEMA)
    if found:
        raise Refusal("the result of {} fails the K3 schema: {}".format(line["id"], "; ".join(found)))
    records.append_json_line(os.path.join(results, CHECKS), result, records.PRIVATE_FILE)
    return status


def ended(step: suite.StepRun) -> str:
    return "\n{}\n".format(step.problem if step.exit is None else "exit {}".format(step.exit))


def reached(
    surfaces: List[Dict[str, Any]], results: str, worktree: str, profile: Dict[str, Any], hidden: credentials.Secrets
) -> Dict[str, bool]:
    commands = [(surface["name"], surface.get("reach")) for surface in surfaces]
    runnable = [(name, command) for name, command in commands if isinstance(command, str) and command.strip()]
    if not runnable:
        return {}
    log_path = os.path.join(results, REACH_EVIDENCE)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    return {name: reaches(command, log_path, worktree, profile, hidden) for name, command in runnable}


def reaches(command: str, log_path: str, worktree: str, profile: Dict[str, Any], hidden: credentials.Secrets) -> bool:
    step = suite.run_step(REACH_STEP, command, worktree, FEATURE, log_path, profile, hidden)
    suite.append_log(log_path, ended(step), hidden)
    return step.exit == 0
