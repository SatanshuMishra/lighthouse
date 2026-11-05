import json
import os
import re
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from lighthouse_tool import handoff, verdict
from lighthouse_tool.repo import Refusal

VERDICT_LINE = "verdict_line"
STRUCTURED_OUTPUT = "structured_output"
SESSION_ID = "session_id"
REPLY_FORMS = ("verdict", "blocked")
VERDICT_FORM = "verdict"
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REPLY = "the reply"
STRUCTURED = "the reply's structured_output"


class Fault(NamedTuple):
    subject: str
    schema: str
    errors: Tuple[str, ...]


class Reading(NamedTuple):
    line: Optional[Dict[str, Any]]
    faults: Tuple[Fault, ...]


def h13_file() -> str:
    return handoff.schema_file(verdict.H13)


def reply_schema_label() -> str:
    return "the reply schema built from {}".format(h13_file())


def form_label(form: str) -> str:
    return "{}#/$defs/{}".format(h13_file(), form)


def form_schema(form: str) -> Dict[str, Any]:
    return {"$ref": form_label(form)}


def reply_schema() -> Dict[str, Any]:
    definitions = handoff.schema_document(verdict.H13).get("$defs")
    missing = [form for form in REPLY_FORMS if not isinstance(definitions, dict) or form not in definitions]
    if missing:
        raise Refusal("the owned format {} has no {} form for the reply schema".format(h13_file(), " or ".join(missing)))
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [VERDICT_LINE],
        "properties": {VERDICT_LINE: {"oneOf": [{"$ref": "#/$defs/" + form} for form in REPLY_FORMS]}},
        "$defs": definitions,
    }


def schema_argument(schema: Dict[str, Any]) -> str:
    return json.dumps(schema, separators=(",", ":"))


def envelope_of(output: bytes) -> Optional[Dict[str, Any]]:
    try:
        envelope = json.loads(output.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(envelope, dict):
        return None
    session = envelope.get(SESSION_ID)
    return envelope if isinstance(session, str) and SESSION_PATTERN.match(session) else None


def read_reply(envelope: Dict[str, Any], results: str, schema: Dict[str, Any]) -> Reading:
    if STRUCTURED_OUTPUT not in envelope:
        return Reading(None, (Fault(REPLY, reply_schema_label(), ("# required: the reply carries no structured_output",)),))
    structured = envelope[STRUCTURED_OUTPUT]
    errors = handoff.document_errors(reply_schema_label(), schema, structured)
    if errors:
        return Reading(None, (Fault(STRUCTURED, reply_schema_label(), tuple(errors)),))
    line = structured[VERDICT_LINE]
    if handoff.document_errors(form_label(VERDICT_FORM), form_schema(VERDICT_FORM), line):
        return Reading(line, ())
    return verdict_reading(line, results)


def verdict_reading(line: Dict[str, Any], results: str) -> Reading:
    written, verdict_faults = checked_file(
        results,
        verdict.VERDICT,
        form_label(VERDICT_FORM),
        lambda value: handoff.document_errors(form_label(VERDICT_FORM), form_schema(VERDICT_FORM), value),
    )
    _, findings_faults = checked_file(
        results,
        verdict.FINDINGS,
        handoff.schema_file(verdict.H14),
        lambda value: handoff.schema_errors(verdict.H14, value),
    )
    faults = findings_faults + verdict_faults
    if faults or written is None:
        return Reading(None, faults)
    return Reading({**written, "pr": line["pr"]}, ())


def checked_file(
    results: str, name: str, label: str, errors_of: Callable[[Any], List[str]]
) -> Tuple[Optional[Dict[str, Any]], Tuple[Fault, ...]]:
    path = os.path.join(results, name)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return None, (Fault(name, label, ("# missing: the child session left no {}".format(name),)),)
    except (OSError, UnicodeDecodeError) as error:
        return None, (Fault(name, label, ("# unreadable: {}".format(getattr(error, "strerror", None) or error),)),)
    try:
        value = json.loads(text)
    except ValueError:
        return None, (Fault(name, label, ("# type: {} is not JSON".format(name),)),)
    errors = errors_of(value)
    if errors:
        return None, (Fault(name, label, tuple(errors)),)
    return value, ()


def described(fault: Fault) -> str:
    return "{} fails {}: {}".format(fault.subject, fault.schema, handoff.joined(list(fault.errors)))


def re_ask_prompt(faults: Tuple[Fault, ...]) -> str:
    return one_line(
        " ".join(
            [
                "Your reply, or a file it left in the results folder, breaks its owned format.",
                *("{}.".format(described(fault)) for fault in faults),
                "Fix every error named here: write findings.json through lighthouse findings and verdict.json through lighthouse verdict,",
                "then reply again with structured output whose verdict_line passes the reply schema.",
            ]
        )
    )


def blocked_reason(faults: Tuple[Fault, ...]) -> str:
    return one_line(
        "the child session's reply still broke its owned format after one re-ask: {}".format(
            "; ".join(described(fault) for fault in faults)
        )
    )


def no_json_reason(kept: str) -> str:
    return "the child session printed no JSON result with a session_id; its output is kept in {}".format(kept)


def one_line(text: str) -> str:
    return " ".join(text.split())
