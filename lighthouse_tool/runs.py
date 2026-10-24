import json
import os
import statistics
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool.records import UnreadableLine, is_number, read_json_lines
from lighthouse_tool.repo import Parser, Refusal, require_root, state_dir
from lighthouse_tool.spend import KINDS

LEDGER = "runs.jsonl"
LAUNCH = "launch"


def parser() -> Parser:
    arguments = Parser(prog="lighthouse runs", add_help=False)
    arguments.add_argument("--repo", required=True)
    return arguments


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        folder = state_dir(require_root(options.repo))
        lines = read_ledger(os.path.join(folder, LEDGER)) if folder is not None else []
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse runs: {}".format(refusal)
    summary = summarised(merged(lines))
    return 0, json.dumps(summary), "lighthouse runs: {} runs".format(summary["runs"])


def read_ledger(path: str) -> List[Dict[str, Any]]:
    try:
        return read_json_lines(path)
    except OSError as error:
        raise Refusal("cannot read {}: {}".format(path, error.strerror or error))
    except UnreadableLine as unreadable:
        raise Refusal("{}; repair or remove that line, then run lighthouse runs again".format(unreadable))


def run_key(index: int, line: Dict[str, Any]) -> str:
    run_id = line.get("run")
    return "run:" + run_id if isinstance(run_id, str) and run_id else "line:{}".format(index)


def merged(lines: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for index, line in enumerate(lines):
        key = run_key(index, line)
        groups[key] = [*groups.get(key, []), line]
    return list(groups.values())


def reported_cost(cost: Any) -> Optional[float]:
    if is_number(cost):
        return float(cost)
    if isinstance(cost, dict) and cost and all(is_number(value) for value in cost.values()):
        return float(sum(cost.values()))
    return None


def last_spend(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    spends = [line["spend"] for line in group if line.get("kind") != LAUNCH and isinstance(line.get("spend"), dict)]
    return spends[-1] if spends else {}


def launches(group: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [line for line in group if line.get("kind") == LAUNCH]


def run_minutes(group: List[Dict[str, Any]]) -> Optional[float]:
    spent = last_spend(group).get("minutes")
    if is_number(spent):
        return spent
    launched = [line["minutes"] for line in launches(group) if is_number(line.get("minutes"))]
    return launched[-1] if launched else None


def run_dollars(group: List[Dict[str, Any]]) -> Optional[float]:
    reported = [reported_cost(line.get("cost")) for line in launches(group)]
    known = [cost for cost in reported if cost is not None]
    if known:
        return known[-1]
    table = last_spend(group).get("dollars")
    return table if is_number(table) else None


def number_in(record: Any, key: str) -> float:
    value = record.get(key) if isinstance(record, dict) else None
    return value if is_number(value) else 0


def totalled(values: List[float], places: int) -> Dict[str, Optional[float]]:
    return {
        "total": round(sum(values), places),
        "median": round(statistics.median(values), places) if values else None,
    }


def step_minutes(spends: List[Dict[str, Any]]) -> Dict[str, float]:
    steps = [
        step
        for spend in spends
        for step in spend.get("steps") or []
        if isinstance(step, dict) and isinstance(step.get("name"), str)
    ]
    names = list(dict.fromkeys(step["name"] for step in steps))
    return {name: round(sum(number_in(step, "minutes") for step in steps if step["name"] == name), 1) for name in names}


def summarised(groups: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    spends = [last_spend(group) for group in groups]
    minutes = [value for value in (run_minutes(group) for group in groups) if value is not None]
    dollars = [value for value in (run_dollars(group) for group in groups) if value is not None]
    token_kinds = {kind: sum(number_in(spend, kind) for spend in spends) for kind in (*KINDS, "tokens")}
    return {
        "runs": len(groups),
        "minutes": totalled(minutes, 1),
        "dollars": totalled(dollars, 6),
        "tokens": token_kinds,
        "steps": step_minutes(spends),
        "waiting_on_person": round(sum(number_in(spend.get("waiting"), "person") for spend in spends), 1),
        "expired_rewrites": {
            "count": sum(number_in(spend.get("expired_rewrites"), "count") for spend in spends),
            "tokens": sum(number_in(spend.get("expired_rewrites"), "tokens") for spend in spends),
        },
    }
