import datetime
import json
import os
import re
from typing import Any, Dict, Iterator, List, NamedTuple, Optional, Tuple
from lighthouse_tool.repo import Parser, Refusal

USAGE_FIELDS = (
    ("input", "input_tokens"),
    ("cache_creation", "cache_creation_input_tokens"),
    ("cache_read", "cache_read_input_tokens"),
    ("output", "output_tokens"),
)

FRACTION = re.compile(r"\.(\d+)")


class Message(NamedTuple):
    identifier: str
    timestamp: datetime.datetime
    usage: Dict[str, Any]


def parser() -> Parser:
    arguments = Parser(prog="lighthouse spend", add_help=False)
    arguments.add_argument("--since", required=True)
    arguments.add_argument("--from", dest="origin")
    arguments.add_argument("--transcripts")
    return arguments


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        since = parse_time(options.since)
        if since is None:
            raise Refusal("--since {} is not an ISO-8601 time".format(options.since))
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse spend: {}".format(refusal)
    folder = options.transcripts or project_folder(options.origin or os.getcwd())
    totals = summed(counted(messages(folder), since), since)
    return 0, json.dumps(totals), "lighthouse spend: {} messages, {} tokens in {} minutes from {}".format(
        totals["messages"], totals["tokens"], totals["minutes"], folder
    )


def project_folder(origin: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(origin))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", name)


def parse_time(text: Any) -> Optional[datetime.datetime]:
    if not isinstance(text, str):
        return None
    normalised = FRACTION.sub(lambda match: "." + (match.group(1) + "000000")[:6], text.strip(), count=1)
    if normalised.endswith(("Z", "z")):
        normalised = normalised[:-1] + "+00:00"
    try:
        moment = datetime.datetime.fromisoformat(normalised)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def transcript_files(folder: str) -> List[str]:
    found = [
        os.path.join(directory, name)
        for directory, _, names in os.walk(folder)
        for name in names
        if name.endswith(".jsonl")
    ]
    return sorted(found)


def messages(folder: str) -> Iterator[Message]:
    for path in transcript_files(folder):
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        for line in lines:
            message = parsed_message(line)
            if message is not None:
                yield message


def parsed_message(line: str) -> Optional[Message]:
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict) or entry.get("type") != "assistant":
        return None
    body = entry.get("message")
    if not isinstance(body, dict):
        return None
    identifier = body.get("id")
    usage = body.get("usage")
    timestamp = parse_time(entry.get("timestamp"))
    if not isinstance(identifier, str) or not identifier or not isinstance(usage, dict) or timestamp is None:
        return None
    return Message(identifier, timestamp, usage)


def counted(found: Iterator[Message], since: datetime.datetime) -> List[Message]:
    after = [message for message in found if message.timestamp > since]
    first_by_identifier = {}
    for message in after:
        first_by_identifier.setdefault(message.identifier, message)
    return list(first_by_identifier.values())


def token_count(usage: Dict[str, Any], field: str) -> int:
    value = usage.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def summed(found: List[Message], since: datetime.datetime) -> Dict[str, Any]:
    sums = {key: sum(token_count(message.usage, field) for message in found) for key, field in USAGE_FIELDS}
    latest = max((message.timestamp for message in found), default=None)
    minutes = 0 if latest is None else round((latest - since).total_seconds() / 60, 1)
    return {
        **sums,
        "tokens": sum(sums.values()),
        "messages": len(found),
        "minutes": minutes,
    }
