import json
from typing import Any, Dict, List, Tuple

from lighthouse_tool import handoff
from lighthouse_tool.repo import Refusal

PRODUCER = "interphase"
K1_SCHEMA = "k1-acceptance.schema.json"

Placed = Tuple[str, Any]


def read_record(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise Refusal("record {} cannot be read: {}".format(path, error.strerror or error))
    try:
        found = json.loads(text)
    except ValueError as error:
        raise Refusal("record {} is not JSON: {}".format(path, error))
    if not isinstance(found, dict):
        raise Refusal("record {} is not a JSON object".format(path))
    return found


def lines_at(path: str) -> List[Dict[str, Any]]:
    return acceptance_lines(read_record(path), path)


def acceptance_lines(record: Dict[str, Any], source: str) -> List[Dict[str, Any]]:
    criteria = record.get("criteria")
    if not isinstance(criteria, list):
        raise Refusal("record {}: #/criteria must be a list of criteria".format(source))
    placed = [
        (pointer, line)
        for number, criterion in enumerate(criteria)
        for pointer, line in criterion_lines(criterion, "#/criteria/{}".format(number), source)
    ]
    checked = [checked_line(pointer, line, source) for pointer, line in placed]
    refuse_repeated_ids(placed, source)
    return checked


def criterion_lines(criterion: Any, pointer: str, source: str) -> List[Placed]:
    if not isinstance(criterion, dict):
        raise Refusal("record {}: {} is not an object".format(source, pointer))
    acceptance = criterion.get("acceptance", [])
    if not isinstance(acceptance, list):
        raise Refusal("record {}: {}/acceptance must be a list of acceptance lines".format(source, pointer))
    return [("{}/acceptance/{}".format(pointer, index), line) for index, line in enumerate(acceptance)]


def line_name(pointer: str, line: Any) -> str:
    identifier = line.get("id") if isinstance(line, dict) else None
    return "{} at {}".format(identifier, pointer) if isinstance(identifier, str) else pointer


def checked_line(pointer: str, line: Any, source: str) -> Dict[str, Any]:
    described = "acceptance line {} of record {}".format(line_name(pointer, line), source)
    return dict(handoff.read_through(PRODUCER, described, K1_SCHEMA, line))


def refuse_repeated_ids(placed: List[Placed], source: str) -> None:
    identifiers = [line["id"] for _, line in placed]
    repeats = [index for index, identifier in enumerate(identifiers) if identifier in identifiers[:index]]
    if repeats:
        pointer, line = placed[repeats[0]]
        raise Refusal(
            "acceptance line {} of record {} repeats the id {}".format(line_name(pointer, line), source, line["id"])
        )
