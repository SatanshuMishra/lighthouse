import glob
import json
import os
import statistics
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool import metrics_writer
from lighthouse_tool.records import is_number
from lighthouse_tool.repo import Parser, Refusal, repository_folder, require_root
from lighthouse_tool.run_record import PLUGIN
from lighthouse_tool.spend import KINDS


def parser() -> Parser:
    arguments = Parser(prog="lighthouse runs", add_help=False)
    arguments.add_argument("--repo", required=True)
    return arguments


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        folder = repository_folder(require_root(options.repo))
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse runs: {}".format(refusal)
    summaries = read_summaries(folder) if folder is not None else []
    summary = summarised(summaries)
    return 0, json.dumps(summary), "lighthouse runs: {} runs".format(summary["runs"])


def read_summary(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as handle:
            line = json.loads(handle.read())
    except (OSError, ValueError):
        return None
    return line if isinstance(line, dict) else None


def read_summaries(folder: str) -> List[Dict[str, Any]]:
    pattern = os.path.join(glob.escape(metrics_writer.store_root(os.environ)), "plugin=" + PLUGIN, "kind=summary", "repo=" + glob.escape(folder), "*.json")
    read = [read_summary(path) for path in sorted(glob.glob(pattern))]
    return [summary for summary in read if summary is not None]


def number_in(record: Any, key: str) -> Optional[float]:
    value = record.get(key) if isinstance(record, dict) else None
    return value if is_number(value) else None


def totalled(values: List[float], places: int) -> Dict[str, Optional[float]]:
    return {
        "total": round(sum(values), places),
        "median": round(statistics.median(values), places) if values else None,
    }


def known(values: List[Optional[float]]) -> List[float]:
    return [value for value in values if value is not None]


def per_minute(seconds: Optional[float]) -> Optional[float]:
    return seconds / 60 if seconds is not None else None


def step_minutes(summaries: List[Dict[str, Any]]) -> Dict[str, float]:
    steps = [
        step
        for summary in summaries
        for step in summary.get("steps") or []
        if isinstance(step, dict) and isinstance(step.get("step"), str)
    ]
    names = list(dict.fromkeys(step["step"] for step in steps))
    return {
        name: round(sum(known([per_minute(number_in(step, "elapsed_seconds")) for step in steps if step["step"] == name])), 1)
        for name in names
    }


def token_kind_total(summaries: List[Dict[str, Any]], kind: str) -> float:
    return sum(known([number_in(summary.get("tokens"), kind) for summary in summaries]))


def summarised(summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    minutes = known([per_minute(number_in(summary, "run_seconds")) for summary in summaries])
    dollars = known([number_in(summary, "usd") for summary in summaries])
    kinds = {kind: token_kind_total(summaries, kind) for kind in KINDS}
    person_minutes = known([per_minute(number_in(summary.get("waiting"), "person_seconds")) for summary in summaries])
    return {
        "runs": len(summaries),
        "minutes": totalled(minutes, 1),
        "dollars": totalled(dollars, 6),
        "tokens": {**kinds, "tokens": sum(kinds.values())},
        "steps": step_minutes(summaries),
        "waiting_on_person": round(sum(person_minutes), 1),
        "expired_rewrites": {
            "count": sum(known([number_in(summary.get("expired_rewrites"), "count") for summary in summaries])),
            "tokens": sum(known([number_in(summary.get("expired_rewrites"), "cache_write") for summary in summaries])),
        },
    }
