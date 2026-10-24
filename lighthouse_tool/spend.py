import datetime
import json
import os
import re
import shlex
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

from lighthouse_tool import mark
from lighthouse_tool.records import UnreadableLine, is_number, json_object, read_json_lines
from lighthouse_tool.repo import Parser, Refusal, require_root

KINDS = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")
WRITE_KINDS = ("cache_write_5m", "cache_write_1h")
PRICES = os.path.join(os.path.dirname(os.path.realpath(__file__)), "prices.json")
SPEND = "spend.json"
FIVE_MINUTES = datetime.timedelta(minutes=5)
ONE_HOUR = datetime.timedelta(hours=1)
PERSON_TOOLS = ("AskUserQuestion",)
PERSON, TOOL, MODEL = "person", "tool", "model"
UNKNOWN_MODEL = "unknown"
SHELL_PUNCTUATION = "();<>|&\n"
SHELL_OPERATOR = re.compile(r"^[();<>|&\n]+$")
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.+)$")
FRACTION = re.compile(r"\.(\d+)")

Tokens = Dict[str, int]
Prices = Dict[str, Dict[str, float]]


class Row(NamedTuple):
    timestamp: datetime.datetime
    entry: Dict[str, Any]


class Transcript(NamedTuple):
    path: str
    cwd: Optional[str]
    rows: List[Row]


class Message(NamedTuple):
    identifier: str
    timestamp: datetime.datetime
    model: str
    tokens: Tokens


class MarkCall(NamedTuple):
    edge: str
    step: str
    build: Optional[str]
    path: Optional[str]
    folder: Optional[str]
    timestamp: datetime.datetime
    written: Optional[datetime.datetime]


class MarkKey(NamedTuple):
    step: str
    build: Optional[str]
    path: Optional[str]


class MarkLine(NamedTuple):
    edge: str
    key: MarkKey
    folder: Optional[str]
    time: datetime.datetime


class Span(NamedTuple):
    key: Tuple[str, int]
    step: str
    build: Optional[str]
    path: Optional[str]
    folder: Optional[str]
    start: datetime.datetime
    minutes: float


class WaitState(NamedTuple):
    pending: Dict[str, str]
    awaiting_prompt: bool


class Reading(NamedTuple):
    messages: List[Message]
    spans: List[Span]
    owners: Dict[str, Tuple[str, int]]
    expired: Tuple[int, int]
    waiting: Dict[str, float]


def parser() -> Parser:
    arguments = Parser(prog="lighthouse spend", add_help=False)
    arguments.add_argument("--since", required=True)
    arguments.add_argument("--from", dest="origin")
    arguments.add_argument("--transcripts")
    arguments.add_argument("--results")
    arguments.add_argument("--repo")
    arguments.add_argument("--prices")
    return arguments


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        since = parse_time(options.since)
        if since is None:
            raise Refusal("--since {} is not an ISO-8601 time".format(options.since))
        if options.repo is not None and options.results is None:
            raise Refusal("--repo needs --results, the folder spend.json is written to")
        if options.repo is not None:
            require_root(options.repo)
        prices = read_prices(options.prices or PRICES)
        scope, transcripts = scoped_transcripts(options)
        marked = read_mark_lines(os.path.realpath(options.results)) if options.results is not None else []
        totals = spend_report(transcripts, since, prices, marked)
        if options.repo is not None:
            write_spend(os.path.realpath(options.results), totals)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse spend: {}".format(refusal)
    return 0, json.dumps(totals), "lighthouse spend: {} messages, {} tokens, {} dollars in {} minutes from {}".format(
        totals["messages"], totals["tokens"], totals["dollars"], totals["minutes"], scope
    )


def claude_projects() -> str:
    return os.path.join(os.path.expanduser("~"), ".claude", "projects")


def mapped_name(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def project_folder(origin: str) -> str:
    return os.path.join(claude_projects(), mapped_name(os.path.abspath(origin)))


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


def read_prices(path: str) -> Prices:
    try:
        with open(path, encoding="utf-8") as handle:
            table = json.load(handle)
    except (OSError, ValueError) as error:
        raise Refusal("the price table {} cannot be read: {}".format(path, error))
    usable = isinstance(table, dict) and all(
        isinstance(rates, dict) and all(is_number(rates.get(kind)) and rates[kind] >= 0 for kind in KINDS)
        for rates in table.values()
    )
    if not usable:
        raise Refusal("the price table {} must give every model a dollar rate for each of {}".format(path, ", ".join(KINDS)))
    return {model: {kind: float(rates[kind]) for kind in KINDS} for model, rates in table.items()}


def write_spend(results: str, totals: Dict[str, Any]) -> None:
    try:
        with open(os.path.join(results, SPEND), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(totals, indent=2) + "\n")
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(os.path.join(results, SPEND), error.strerror or error))


def is_inside(folder: str, path: str) -> bool:
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def scoped_transcripts(options: Any) -> Tuple[str, List[Transcript]]:
    if options.results is None:
        folder = options.transcripts or project_folder(options.origin or os.getcwd())
        return folder, [read_transcript(path) for path in transcript_files(folder)]
    results = os.path.realpath(options.results)
    base = options.transcripts or claude_projects()
    prefixes = {mapped_name(os.path.abspath(options.results)), mapped_name(results)}
    candidates = [os.path.join(base, name) for name in listed(base) if name.startswith(tuple(prefixes))]
    found = [read_transcript(path) for folder in candidates for path in transcript_files(folder)]
    return results, [transcript for transcript in found if transcript.cwd is not None and is_inside(results, transcript.cwd)]


def listed(base: str) -> List[str]:
    try:
        return sorted(name for name in os.listdir(base) if os.path.isdir(os.path.join(base, name)))
    except OSError:
        return []


def transcript_files(folder: str) -> List[str]:
    found = [
        os.path.join(directory, name)
        for directory, _, names in os.walk(folder)
        for name in names
        if name.endswith(".jsonl")
    ]
    return sorted(found)


def parsed_entries(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return []
    entries = [json_object(line) for line in lines]
    return [entry for entry in entries if entry is not None]


def read_transcript(path: str) -> Transcript:
    entries = parsed_entries(path)
    cwds = [entry["cwd"] for entry in entries if isinstance(entry.get("cwd"), str) and entry["cwd"]]
    timed = [(parse_time(entry.get("timestamp")), entry) for entry in entries]
    rows = sorted((Row(moment, entry) for moment, entry in timed if moment is not None), key=lambda row: row.timestamp)
    return Transcript(path, os.path.realpath(cwds[0]) if cwds else None, rows)


def body_of(entry: Dict[str, Any]) -> Dict[str, Any]:
    body = entry.get("message")
    return body if isinstance(body, dict) else {}


def blocks_of(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    content = body_of(entry).get("content")
    return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []


def message_id(entry: Dict[str, Any]) -> Optional[str]:
    identifier = body_of(entry).get("id")
    return identifier if entry.get("type") == "assistant" and isinstance(identifier, str) and identifier else None


def token_count(usage: Dict[str, Any], field: str) -> int:
    value = usage.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def tokens_of(usage: Dict[str, Any]) -> Tokens:
    split = usage.get("cache_creation")
    has_split = isinstance(split, dict) and any(
        field in split for field in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")
    )
    five_minute = token_count(split, "ephemeral_5m_input_tokens") if has_split else token_count(usage, "cache_creation_input_tokens")
    one_hour = token_count(split, "ephemeral_1h_input_tokens") if has_split else 0
    return {
        "input": token_count(usage, "input_tokens"),
        "cache_write_5m": five_minute,
        "cache_write_1h": one_hour,
        "cache_read": token_count(usage, "cache_read_input_tokens"),
        "output": token_count(usage, "output_tokens"),
    }


def parsed_message(row: Row) -> Optional[Message]:
    identifier = message_id(row.entry)
    body = body_of(row.entry)
    usage = body.get("usage")
    if identifier is None or not isinstance(usage, dict):
        return None
    model = body.get("model")
    return Message(identifier, row.timestamp, model if isinstance(model, str) and model else UNKNOWN_MODEL, tokens_of(usage))


def written(message: Message) -> int:
    return sum(message.tokens[kind] for kind in WRITE_KINDS)


def expired_rewrites(messages: List[Message]) -> Tuple[int, int]:
    lifetime = ONE_HOUR if any(message.tokens["cache_write_1h"] > 0 for message in messages) else FIVE_MINUTES
    rewrites = [
        later
        for earlier, later in zip(messages, messages[1:])
        if written(later) > 0 and later.timestamp - earlier.timestamp > lifetime
    ]
    return len(rewrites), sum(written(message) for message in rewrites)


def is_typed_prompt(entry: Dict[str, Any]) -> bool:
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    content = body_of(entry).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    kinds = {block.get("type") for block in blocks_of(entry)}
    return "text" in kinds and "tool_result" not in kinds


def opened_tools(entry: Dict[str, Any]) -> Dict[str, str]:
    return {
        block["id"]: PERSON if block.get("name") in PERSON_TOOLS else TOOL
        for block in blocks_of(entry)
        if block.get("type") == "tool_use" and isinstance(block.get("id"), str)
    }


def answered_tools(entry: Dict[str, Any]) -> Set[str]:
    return {block.get("tool_use_id") for block in blocks_of(entry) if block.get("type") == "tool_result"}


def advanced(state: WaitState, row: Row, ends_turn: bool) -> WaitState:
    if row.entry.get("type") == "assistant":
        return WaitState({**state.pending, **opened_tools(row.entry)}, ends_turn)
    answered = answered_tools(row.entry)
    pending = {identifier: kind for identifier, kind in state.pending.items() if identifier not in answered}
    return WaitState(pending, state.awaiting_prompt and not is_typed_prompt(row.entry))


def waiting_on(state: WaitState) -> str:
    if PERSON in state.pending.values():
        return PERSON
    if state.pending:
        return TOOL
    return PERSON if state.awaiting_prompt else MODEL


def waiting_seconds(rows: List[Row]) -> Dict[str, float]:
    conversation = [row for row in rows if row.entry.get("type") in ("user", "assistant")]
    last_row_of = {message_id(row.entry): index for index, row in enumerate(conversation)}
    seconds = {PERSON: 0.0, TOOL: 0.0, MODEL: 0.0}
    state = WaitState({}, False)
    for index, (row, following) in enumerate(zip(conversation, conversation[1:])):
        stop_reason = body_of(row.entry).get("stop_reason")
        ends_turn = stop_reason == "end_turn" and last_row_of.get(message_id(row.entry)) == index
        state = advanced(state, row, ends_turn)
        category = waiting_on(state)
        seconds = {**seconds, category: seconds[category] + (following.timestamp - row.timestamp).total_seconds()}
    return seconds


def command_tokens(command: str) -> List[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=SHELL_PUNCTUATION)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    try:
        return list(lexer)
    except ValueError:
        return []


def is_lighthouse(word: str) -> bool:
    return word == "lighthouse" or word == "bin/lighthouse" or word.endswith("/bin/lighthouse")


def lighthouse_variables(words: List[str]) -> Set[str]:
    assigned = [ASSIGNMENT.match(word) for word in words]
    names = {found.group(1) for found in assigned if found is not None and is_lighthouse(found.group(2))}
    return {form.format(name) for name in names for form in ("${}", "${{{}}}")}


def mark_arguments(command: str) -> List[List[str]]:
    words = command_tokens(command)
    variables = lighthouse_variables(words)
    starts = [
        index + 2
        for index, word in enumerate(words[:-1])
        if (is_lighthouse(word) or word in variables) and words[index + 1] == "mark"
    ]
    ends = [next((index for index in range(start, len(words)) if SHELL_OPERATOR.match(words[index])), len(words)) for start in starts]
    return [words[start:end] for start, end in zip(starts, ends)]


def parsed_mark(arguments: List[str], timestamp: datetime.datetime) -> Optional[MarkCall]:
    try:
        options = mark.parser().parse_args(arguments)
    except Refusal:
        return None
    return MarkCall(options.edge, options.step, options.build, options.path, None, timestamp, None)


def text_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def mark_line(line: Dict[str, Any]) -> Optional[MarkLine]:
    moment = parse_time(line.get("time"))
    edge, step = line.get("edge"), line.get("step")
    if edge not in mark.EDGES or not isinstance(step, str) or moment is None:
        return None
    key = MarkKey(step, text_or_none(line.get("build")), text_or_none(line.get("path")))
    return MarkLine(edge, key, text_or_none(line.get("folder")), moment)


def read_mark_lines(results: str) -> List[MarkLine]:
    path = os.path.join(results, mark.MARKS)
    try:
        lines = read_json_lines(path)
    except OSError as error:
        raise Refusal("cannot read {}: {}".format(path, error.strerror or error))
    except UnreadableLine as unreadable:
        raise Refusal("{}; repair or remove that line, then run lighthouse spend again".format(unreadable))
    found = [mark_line(line) for line in lines]
    return [line for line in found if line is not None]


def located(call: MarkCall, marked: List[MarkLine], used: Set[int]) -> Tuple[MarkCall, Set[int]]:
    candidates = [
        (index, line)
        for index, line in enumerate(marked)
        if index not in used
        and line.edge == call.edge
        and line.key == mark_key(call)
        and line.time >= call.timestamp
    ]
    earliest = min(candidates, key=lambda candidate: candidate[1].time, default=None)
    if earliest is None:
        return call, used
    index, line = earliest
    return call._replace(folder=line.folder, written=line.time), used | {index}


def mark_calls(row: Row) -> List[MarkCall]:
    commands = [
        block["input"]["command"]
        for block in blocks_of(row.entry)
        if block.get("type") == "tool_use"
        and block.get("name") == "Bash"
        and isinstance(block.get("input"), dict)
        and isinstance(block["input"].get("command"), str)
    ]
    calls = [parsed_mark(arguments, row.timestamp) for command in commands for arguments in mark_arguments(command)]
    return [call for call in calls if call is not None]


def span_of(key: Tuple[str, int], call: MarkCall, ended: datetime.datetime) -> Span:
    minutes = (ended - call.timestamp).total_seconds() / 60
    return Span(key, call.step, call.build, call.path, call.folder, call.timestamp, minutes)


def ended_span(key: Tuple[str, int], start: MarkCall, end: MarkCall) -> Span:
    if start.written is not None and end.written is not None:
        span = span_of(key, start, end.timestamp)
        return span._replace(minutes=(end.written - start.written).total_seconds() / 60)
    return span_of(key, start, end.timestamp)


def message_calls(rows: List[Row]) -> Dict[str, List[MarkCall]]:
    identified = [(message_id(row.entry), row) for row in rows]
    identifiers = list(dict.fromkeys(identifier for identifier, _ in identified if identifier is not None))
    return {
        identifier: [call for found, row in identified if found == identifier for call in mark_calls(row)]
        for identifier in identifiers
    }


def mark_key(call: MarkCall) -> MarkKey:
    return MarkKey(call.step, call.build, call.path)


def read_marks(
    transcript: Transcript, counted: Set[str], marked: List[MarkLine]
) -> Tuple[List[Span], Dict[str, Tuple[str, int]]]:
    opened: List[Tuple[Tuple[str, int], MarkCall]] = []
    spans: List[Span] = []
    owners: Dict[str, Tuple[str, int]] = {}
    used: Set[int] = set()
    started = 0
    calls_of = message_calls(transcript.rows)
    for row in transcript.rows:
        identifier = message_id(row.entry)
        if identifier is not None and identifier not in calls_of:
            continue
        calls = mark_calls(row) if identifier is None else calls_of.pop(identifier)
        holder = opened[-1][0] if opened else None
        opened_here: List[Tuple[str, int]] = []
        for call in calls:
            found, used = located(call, marked, used)
            if found.edge == "start":
                key = (transcript.path, started)
                opened.append((key, found))
                opened_here.append(key)
                started += 1
                continue
            matching = [index for index, (_, start) in enumerate(opened) if mark_key(start) == mark_key(found)]
            if matching:
                key, start = opened.pop(matching[-1])
                spans.append(ended_span(key, start, found))
        owner = opened_here[-1] if opened_here else holder
        if identifier is not None and identifier in counted and owner is not None:
            owners[identifier] = owner
    last = transcript.rows[-1].timestamp if transcript.rows else None
    unended = [span_of(key, start, last or start.timestamp) for key, start in opened]
    return spans + unended, owners


def transcript_messages(transcript: Transcript, since: datetime.datetime) -> List[Message]:
    found = [parsed_message(row) for row in transcript.rows if row.timestamp > since]
    first_by_identifier: Dict[str, Message] = {}
    for message in found:
        if message is not None:
            first_by_identifier.setdefault(message.identifier, message)
    return sorted(first_by_identifier.values(), key=lambda message: message.timestamp)


def owned_messages(transcripts: List[Transcript], since: datetime.datetime) -> List[List[Message]]:
    claimed: Set[str] = set()
    owned = []
    for transcript in transcripts:
        fresh = [message for message in transcript_messages(transcript, since) if message.identifier not in claimed]
        claimed.update(message.identifier for message in fresh)
        owned.append(fresh)
    return owned


def recent(transcript: Transcript, since: datetime.datetime) -> Transcript:
    return Transcript(transcript.path, transcript.cwd, [row for row in transcript.rows if row.timestamp > since])


def folder_owner(transcript: Transcript, spans: List[Span]) -> Optional[Tuple[str, int]]:
    holding = [
        span
        for span in spans
        if span.folder is not None and span.key[0] != transcript.path and transcript.cwd is not None and is_inside(span.folder, transcript.cwd)
    ]
    deepest = max(holding, key=lambda span: len(span.folder or ""), default=None)
    return deepest.key if deepest is not None else None


def reading(transcripts: List[Transcript], since: datetime.datetime, folders: List[MarkLine]) -> Reading:
    windows = [recent(transcript, since) for transcript in transcripts]
    owned = owned_messages(windows, since)
    marked = [
        read_marks(window, {message.identifier for message in messages}, folders) for window, messages in zip(windows, owned)
    ]
    spans = [span for transcript_spans, _ in marked for span in transcript_spans]
    folder_owners = [folder_owner(window, spans) for window in windows]
    owners = {
        message.identifier: folder_key if folder_key is not None else transcript_owners[message.identifier]
        for messages, (_, transcript_owners), folder_key in zip(owned, marked, folder_owners)
        for message in messages
        if folder_key is not None or message.identifier in transcript_owners
    }
    rewrites = [expired_rewrites(messages) for messages in owned]
    waits = [waiting_seconds(window.rows) for window in windows]
    return Reading(
        messages=[message for messages in owned for message in messages],
        spans=spans,
        owners=owners,
        expired=(sum(count for count, _ in rewrites), sum(tokens for _, tokens in rewrites)),
        waiting={kind: sum(wait[kind] for wait in waits) for kind in (PERSON, TOOL, MODEL)},
    )


def summed_tokens(messages: Iterable[Message]) -> Tokens:
    listed_messages = list(messages)
    return {kind: sum(message.tokens[kind] for message in listed_messages) for kind in KINDS}


def model_dollars(model: str, tokens: Tokens, prices: Prices) -> Optional[float]:
    if not any(tokens.values()):
        return 0.0
    rates = prices.get(model)
    if rates is None:
        return None
    return round(sum(tokens[kind] * rates[kind] for kind in KINDS) / 1000000, 6)


def by_model(messages: List[Message]) -> Dict[str, Tokens]:
    models = sorted({message.model for message in messages})
    return {model: summed_tokens(message for message in messages if message.model == model) for model in models}


def costed(messages: List[Message], prices: Prices) -> Dict[str, Any]:
    tokens = summed_tokens(messages)
    dollars = [model_dollars(model, kinds, prices) for model, kinds in by_model(messages).items()]
    total = None if None in dollars else round(sum(amount for amount in dollars if amount is not None), 6)
    return {**tokens, "tokens": sum(tokens.values()), "dollars": total}


def models_report(messages: List[Message], prices: Prices) -> Dict[str, Dict[str, Any]]:
    return {
        model: {**kinds, "tokens": sum(kinds.values()), "dollars": model_dollars(model, kinds, prices)}
        for model, kinds in by_model(messages).items()
    }


def group_of(span: Span, by_path: bool) -> Tuple[str, Optional[str]]:
    return (span.path or "") if by_path else span.step, span.build


def group_row(
    group: Tuple[str, Optional[str]],
    spans: List[Span],
    messages: List[Message],
    owners: Dict[str, Tuple[str, int]],
    prices: Prices,
    by_path: bool,
) -> Dict[str, Any]:
    name, build = group
    keys = {span.key for span in spans}
    minutes = sum(span.minutes for span in spans if (span.path is not None) == by_path)
    attributed = [message for message in messages if owners.get(message.identifier) in keys]
    return {"name": name, "build": build, "minutes": round(minutes, 1), **costed(attributed, prices)}


def grouped(
    spans: List[Span], messages: List[Message], owners: Dict[str, Tuple[str, int]], prices: Prices, by_path: bool
) -> List[Dict[str, Any]]:
    members = [span for span in spans if span.path is not None or not by_path]
    groups = {group_of(span, by_path) for span in members}
    first_start = {group: min(span.start for span in members if group_of(span, by_path) == group) for group in groups}
    return [
        group_row(group, [span for span in members if group_of(span, by_path) == group], messages, owners, prices, by_path)
        for group in sorted(groups, key=lambda group: (first_start[group], group[0]))
    ]


def spend_report(
    transcripts: List[Transcript], since: datetime.datetime, prices: Prices, marked: List[MarkLine]
) -> Dict[str, Any]:
    found = reading(transcripts, since, marked)
    models = models_report(found.messages, prices)
    latest = max((message.timestamp for message in found.messages), default=None)
    minutes = 0 if latest is None else round((latest - since).total_seconds() / 60, 1)
    return {
        **costed(found.messages, prices),
        "messages": len(found.messages),
        "minutes": minutes,
        "models": models,
        "unpriced": [model for model, report in models.items() if report["dollars"] is None],
        "expired_rewrites": {"count": found.expired[0], "tokens": found.expired[1]},
        "waiting": {kind: round(seconds / 60, 1) for kind, seconds in found.waiting.items()},
        "steps": grouped(found.spans, found.messages, found.owners, prices, by_path=False),
        "paths": grouped(found.spans, found.messages, found.owners, prices, by_path=True),
        "shared": costed([message for message in found.messages if message.identifier not in found.owners], prices),
    }
