import json
import os
from typing import Any, List, Optional, Tuple

from lighthouse_tool import handoff
from lighthouse_tool.records import write_atomically
from lighthouse_tool.repo import Parser, Refusal

Outcome = Tuple[int, Optional[str], Optional[str]]

DRAFT = "findings.draft.json"
FINDINGS = "findings.json"
H14 = "h14-lighthouse-findings"


class DraftRefusal(Refusal):
    def __init__(self, message: str, errors: Tuple[str, ...]) -> None:
        super().__init__(message)
        self.errors = errors


def parser() -> Parser:
    arguments = Parser(prog="lighthouse findings", add_help=False)
    arguments.add_argument("--results", required=True)
    return arguments


def run(argv: List[str]) -> Outcome:
    try:
        options = parser().parse_args(argv[1:])
        written = written_findings(results_folder(options.results))
    except DraftRefusal as refusal:
        printed = {"error": str(refusal), "schema": H14, "errors": list(refusal.errors)}
        return 2, json.dumps(printed), "lighthouse findings: {}".format(refusal)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse findings: {}".format(refusal)
    return 0, json.dumps({"written": written}), "lighthouse findings: {} meets {}".format(written, H14)


def results_folder(given: str) -> str:
    results = os.path.realpath(given)
    if not os.path.isdir(results):
        raise Refusal("--results {} is not a folder".format(given))
    return results


def written_findings(results: str) -> str:
    draft_path = os.path.join(results, DRAFT)
    draft = checked_draft(draft_path, read_draft(draft_path))
    target = os.path.join(results, FINDINGS)
    try:
        write_atomically(target, json.dumps(draft, indent=2) + "\n")
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(target, error.strerror or error))
    return target


def read_draft(draft_path: str) -> Any:
    try:
        with open(draft_path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        raise refused(draft_path, "{} does not exist; write the findings draft there first".format(DRAFT))
    except OSError as error:
        raise refused(draft_path, "{} cannot be read: {}".format(DRAFT, error.strerror or error))
    try:
        return json.loads(text)
    except ValueError as error:
        raise refused(draft_path, "{} is not JSON: {}".format(DRAFT, error))


def refused(draft_path: str, problem: str) -> DraftRefusal:
    return DraftRefusal(
        "the findings draft {} cannot be checked against {}: {}".format(draft_path, handoff.schema_file(H14), problem),
        (problem,),
    )


def checked_draft(draft_path: str, draft: Any) -> Any:
    errors = handoff.schema_errors(H14, draft)
    if errors:
        raise DraftRefusal(
            "the findings draft {} fails {}, so {} was not written: {}".format(
                draft_path, handoff.schema_file(H14), FINDINGS, handoff.joined(errors)
            ),
            tuple(errors),
        )
    return draft
