import json
from typing import Any, Dict, List, Tuple

from lighthouse_tool import handoff
from lighthouse_tool.repo import Refusal

PRODUCER = "interphase"
H11_SCHEMA = "h11-interphase-record.schema.json"

Placed = Tuple[str, Dict[str, Any]]


def read_record(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise Refusal("record {} cannot be read: {}".format(path, error.strerror or error))
    try:
        return json.loads(text)
    except ValueError as error:
        raise Refusal("record {} is not JSON: {}".format(path, error))


def lines_at(path: str) -> List[Dict[str, Any]]:
    return acceptance_lines(read_record(path), path)


def acceptance_lines(record: Any, source: str) -> List[Dict[str, Any]]:
    checked = handoff.read_through(PRODUCER, "record {}".format(source), H11_SCHEMA, record)
    placed = [
        ("#/criteria/{}/acceptance/{}".format(number, index), line)
        for number, criterion in enumerate(checked["criteria"])
        for index, line in enumerate(criterion.get("acceptance", []))
    ]
    refuse_repeated_ids(placed, source)
    return [dict(line) for _, line in placed]


def refuse_repeated_ids(placed: List[Placed], source: str) -> None:
    identifiers = [line["id"] for _, line in placed]
    repeats = [index for index, identifier in enumerate(identifiers) if identifier in identifiers[:index]]
    if repeats:
        pointer, line = placed[repeats[0]]
        raise Refusal(
            "acceptance line {} at {} of record {} repeats the id {}".format(line["id"], pointer, source, line["id"])
        )
