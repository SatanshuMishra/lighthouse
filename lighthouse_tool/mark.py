import json
import os
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool.records import PRIVATE_FILE, append_json_line, utc_now
from lighthouse_tool.repo import Parser, Refusal

MARKS = "marks.jsonl"
BUILDS = ("core", "feature")
EDGES = ("start", "end")


def parser() -> Parser:
    arguments = Parser(prog="lighthouse mark", add_help=False)
    arguments.add_argument("--results", required=True)
    arguments.add_argument("--step", required=True)
    arguments.add_argument("--build", choices=BUILDS)
    arguments.add_argument("--path")
    arguments.add_argument("--folder")
    arguments.add_argument("edge", choices=EDGES)
    return arguments


def mark_line(options: Any, time: str) -> Dict[str, Any]:
    if not options.step.strip():
        raise Refusal("--step needs the name of the step")
    return {
        "step": options.step,
        "build": options.build,
        "path": options.path,
        "folder": os.path.realpath(options.folder) if options.folder else None,
        "edge": options.edge,
        "time": time,
    }


def append_mark(results: str, line: Dict[str, Any]) -> None:
    try:
        os.makedirs(results, exist_ok=True)
        append_json_line(os.path.join(results, MARKS), line, PRIVATE_FILE)
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(os.path.join(results, MARKS), error.strerror or error))


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        line = mark_line(options, utc_now())
        append_mark(os.path.realpath(options.results), line)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse mark: {}".format(refusal)
    return 0, json.dumps(line), None
