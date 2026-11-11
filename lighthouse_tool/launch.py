import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from lighthouse_tool import child_reply, findings as findings_tool, metrics_writer, noninteractive, process_tree
from lighthouse_tool import results as run_files, run_record, suite, verdict
from lighthouse_tool.records import is_number, write_atomically
from lighthouse_tool.repo import Parser, Refusal, require_root, toplevel

Outcome = Tuple[int, Optional[str], Optional[str]]
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
WORK = "work"
CHILD = "child.json"
CHILD_OUT = "child.out"
LAUNCH = "launch.json"
EARLIER_RUN_FILES = (
    LAUNCH,
    CHILD,
    CHILD_OUT,
    findings_tool.FINDINGS,
    findings_tool.DRAFT,
    verdict.VERDICT,
    run_files.CHECKS,
    run_files.PLAN,
    run_files.RECORD,
    *(name for name in run_record.RESULTS_SOURCES if name != findings_tool.FINDINGS),
    *(build + suffix for build in suite.BUILDS for suffix in (suite.START_PID_SUFFIX, suite.START_EXIT_SUFFIX)),
)
CAFFEINATE = "caffeinate"
SYSTEMD_INHIBIT = "systemd-inhibit"
NO_KEEP_AWAKE = "none"
DARWIN_PROCESS_SELECTOR = 4
PATH_FLAGS = ("repo", "results", "previous", "spec", "record")
CHILD_STORE = "plugin-metrics"
LONGEST_BASH_TIMEOUT = "BASH_MAX_TIMEOUT_MS"
DEFAULT_BASH_TIMEOUT = "BASH_DEFAULT_TIMEOUT_MS"
ONE_WEEK_MS = 7 * 24 * 60 * 60 * 1000


class ChildRun(NamedTuple):
    exit: Optional[int]
    output: bytes
    problem: Optional[str]
    seconds: float
    errors: bytes = b""


class Child(NamedTuple):
    work: str
    keep_awake: str
    environment: Dict[str, str]


class Call(NamedTuple):
    run: ChildRun
    envelope: Optional[Dict[str, Any]]


class Answer(NamedTuple):
    line: Optional[Dict[str, Any]]
    reason: Optional[str]
    faults: Tuple[child_reply.Fault, ...]


class Conversation(NamedTuple):
    calls: Tuple[Call, ...]
    line: Optional[Dict[str, Any]]
    reason: Optional[str]


class ModelCosts(NamedTuple):
    cost: Dict[str, float]
    unpriced: Tuple[str, ...]


def parser() -> Parser:
    arguments = Parser(prog="lighthouse launch", add_help=False)
    for flag in ("--repo", "--core", "--feature", "--results"):
        arguments.add_argument(flag, required=True)
    arguments.add_argument("--previous")
    arguments.add_argument("--spec")
    arguments.add_argument("--record")
    arguments.add_argument("--parent")
    arguments.add_argument("--final", action="store_true")
    return arguments


def located_parser() -> Parser:
    arguments = Parser(prog="lighthouse launch", add_help=False)
    for flag in ("--repo", "--core", "--feature", "--results", "--previous", "--spec", "--record", "--parent"):
        arguments.add_argument(flag)
    arguments.add_argument("--final", action="store_true")
    return arguments


class Located(NamedTuple):
    root: Optional[str]
    results: Optional[str]
    options: Optional[argparse.Namespace]


def located_run(arguments: List[str]) -> Located:
    try:
        located, _ = located_parser().parse_known_args(arguments)
    except Refusal:
        return Located(None, None, None)
    root = toplevel(located.repo) if located.repo is not None else None
    if located.results is None:
        return Located(root, None, located)
    guarded = root if root is not None else enclosing_checkout(located.results)
    if guarded is not None and suite.is_inside(guarded, located.results):
        return Located(root, None, located)
    return Located(root, os.path.realpath(located.results), located)


def enclosing_checkout(path: str) -> Optional[str]:
    folder = os.path.realpath(path)
    while not os.path.isdir(folder) and os.path.dirname(folder) != folder:
        folder = os.path.dirname(folder)
    return toplevel(folder)


def run(argv: List[str]) -> Outcome:
    located = located_run(argv[1:])
    recording = run_record.begun(located.root, located.options)
    cleared = None
    try:
        if located.results is not None:
            refuse_previous_as_results(located)
            clear_earlier_run(located.results)
            cleared = located.results
        options = parser().parse_args(argv[1:])
        return launch(options, recording)
    except (Refusal, OSError) as problem:
        reason = refusal_reason(problem)
        ending = run_record.Ending(blocked_text(reason), reason, None, None)
        return refused(located.results, reason, run_record.finished(recording, cleared, ending))


def refused(results: Optional[str], reason: str, warnings: Tuple[str, ...]) -> Outcome:
    if results is not None:
        leave_blocked_line(results, reason)
    return 2, json.dumps({"error": reason}), with_warnings("lighthouse launch: {}".format(reason), warnings)


def with_warnings(told: str, warnings: Tuple[str, ...]) -> str:
    return "\n".join((told, *warnings))


def refusal_reason(problem: Exception) -> str:
    if isinstance(problem, OSError):
        return "cannot use {}: {}".format(problem.filename or "the results folder", problem.strerror or problem)
    return str(problem)


def refuse_previous_as_results(located: Located) -> None:
    previous = located.options.previous if located.options is not None else None
    if previous is not None and os.path.realpath(previous) == located.results:
        raise Refusal("the --previous and --results folders must differ; give the new run its own results folder")


def clear_earlier_run(results: str) -> None:
    for name in EARLIER_RUN_FILES:
        path = os.path.join(results, name)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as error:
            raise Refusal("cannot clear {} from an earlier run: {}".format(path, error.strerror or error))


def leave_blocked_line(results: str, reason: str) -> None:
    try:
        os.makedirs(results, exist_ok=True)
        write_text(os.path.join(results, LAUNCH), blocked_text(reason) + "\n")
    except (OSError, Refusal):
        pass


def launch(options: argparse.Namespace, recording: Optional[run_record.Recording]) -> Outcome:
    root = require_root(options.repo)
    if suite.is_inside(root, options.results):
        raise Refusal(
            "the results folder {} is inside the repository {}; choose a folder outside it".format(options.results, root)
        )
    work = os.path.join(os.path.abspath(options.results), WORK)
    os.makedirs(work, exist_ok=True)
    results = os.path.realpath(options.results)
    copy_record(results, options)
    keep_awake = keep_awake_tool()
    schema = child_reply.reply_schema()
    talk = conversation(options, schema, Child(work, keep_awake, child_environment(results)), results)
    costs = model_costs(talk.calls)
    record = child_record(talk.calls, costs, keep_awake)
    write_json(os.path.join(results, CHILD), record)
    last = talk.calls[-1].run
    session = record["session_id"]
    try:
        printed = printed_line(talk)
    except Refusal as problem:
        reason = str(problem)
        ending = run_record.Ending(blocked_text(reason), reason, last.exit, session)
        return refused(results, reason, run_record.finished(recording, results, ending))
    warnings = run_record.finished(recording, results, run_record.Ending(printed, talk.reason, last.exit, session))
    try:
        write_text(os.path.join(results, LAUNCH), printed + "\n")
    except Refusal as problem:
        return refused(results, str(problem), warnings)
    summary = summary_text(talk)
    told = summary if talk.reason is None else "{}; blocked: {}".format(summary, talk.reason)
    return 0, printed, with_warnings(told, (*unpriced_warnings(costs.unpriced), *warnings))


def conversation(options: argparse.Namespace, schema: Dict[str, Any], child: Child, results: str) -> Conversation:
    first = called(child_command(options, schema), child)
    answer = answered(first, results, schema)
    if not answer.faults:
        return Conversation((first,), answer.line, answer.reason)
    session = first.envelope[child_reply.SESSION_ID] if first.envelope is not None else ""
    second = called(resumed_command(session, child_reply.re_ask_prompt(answer.faults), schema), child)
    again = answered(second, results, schema)
    reason = child_reply.blocked_reason(again.faults) if again.faults else again.reason
    return Conversation((first, second), again.line if not again.faults else None, reason)


def called(command: List[str], child: Child) -> Call:
    ran = run_child(command, child.work, child.keep_awake, child.environment)
    return Call(ran, child_reply.envelope_of(ran.output) if ran.problem is None else None)


def answered(call: Call, results: str, schema: Dict[str, Any]) -> Answer:
    if call.run.problem is not None:
        return Answer(None, call.run.problem, ())
    if call.envelope is None:
        kept = os.path.join(results, CHILD_OUT)
        write_bytes(kept, call.run.output + call.run.errors)
        return Answer(None, child_reply.no_json_reason(kept), ())
    reading = child_reply.read_reply(call.envelope, results, schema)
    return Answer(reading.line, None, reading.faults)


def printed_line(talk: Conversation) -> str:
    if talk.line is not None:
        return json.dumps(verdict.checked_line("the line lighthouse launch prints", talk.line))
    return blocked_text(talk.reason or "the child session gave no reply")


def summary_text(talk: Conversation) -> str:
    exits = [call.run.exit for call in talk.calls]
    if len(exits) == 1:
        return "lighthouse launch: the child exited {}".format(exits[0])
    return "lighthouse launch: the child exited {}, was re-asked once in the same session and exited {}".format(*exits)


def unpriced_warnings(unpriced: Tuple[str, ...]) -> Tuple[str, ...]:
    return tuple(
        "lighthouse launch: the child's cost report gives no number costUSD for {}; child.json lists it under unpriced".format(model)
        for model in unpriced
    )


def copy_record(results: str, options: argparse.Namespace) -> None:
    source = os.path.abspath(options.record) if options.record is not None else run_files.record_beside(spec_path(options))
    if source is None:
        return
    try:
        shutil.copyfile(source, os.path.join(results, run_files.RECORD))
    except OSError as error:
        raise Refusal("cannot copy the record {}: {}".format(source, error.strerror or error))


def spec_path(options: argparse.Namespace) -> Optional[str]:
    return os.path.abspath(options.spec) if options.spec is not None else None


def child_environment(results: str) -> Dict[str, str]:
    inherited = noninteractive.environment(run_record.environment_without_parent())
    return {
        **{name: value for name, value in inherited.items() if name != DEFAULT_BASH_TIMEOUT},
        LONGEST_BASH_TIMEOUT: str(ONE_WEEK_MS),
        metrics_writer.ROOT_VARIABLE: os.path.join(results, CHILD_STORE),
    }


def test_flags(options: argparse.Namespace) -> List[str]:
    named = [
        ("--" + flag, os.path.abspath(value) if flag in PATH_FLAGS else value)
        for flag, value in (
            ("repo", options.repo),
            ("core", options.core),
            ("feature", options.feature),
            ("results", options.results),
            ("previous", options.previous),
            ("spec", options.spec),
            ("record", options.record),
        )
        if value is not None
    ]
    quoted = [part for flag, value in named for part in (flag, shlex.quote(value))]
    return quoted + (["--final"] if options.final else [])


def child_command(options: argparse.Namespace, schema: Dict[str, Any]) -> List[str]:
    return ["claude", "-p", " ".join(["/lighthouse:test", "--child", *test_flags(options)]), *child_flags(schema)]


def resumed_command(session: str, prompt: str, schema: Dict[str, Any]) -> List[str]:
    return ["claude", "-p", prompt, "--resume", session, *child_flags(schema)]


def child_flags(schema: Dict[str, Any]) -> List[str]:
    return [
        "--model",
        "opus",
        "--plugin-dir",
        PLUGIN_ROOT,
        "--permission-mode",
        "bypassPermissions",
        "--disallowedTools",
        "AskUserQuestion",
        "--output-format",
        "json",
        "--json-schema",
        child_reply.schema_argument(schema),
    ]


def keep_awake_tool() -> str:
    if sys.platform == "darwin" and shutil.which(CAFFEINATE):
        return CAFFEINATE
    if sys.platform.startswith("linux") and shutil.which(SYSTEMD_INHIBIT):
        return SYSTEMD_INHIBIT
    return NO_KEEP_AWAKE


def wrapped(command: List[str], keep_awake: str) -> List[str]:
    if keep_awake == SYSTEMD_INHIBIT:
        return [SYSTEMD_INHIBIT, "--what=idle:sleep", "--why=lighthouse", *command]
    return command


def run_child(command: List[str], work: str, keep_awake: str, environment: Dict[str, str]) -> ChildRun:
    started = time.monotonic()
    with ExitStack() as guarding, ExitStack() as owning:
        try:
            process = owning.enter_context(
                process_tree.started(
                    wrapped(command, keep_awake),
                    0.0,
                    cwd=work,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
        except OSError as error:
            return ChildRun(None, b"", "the child session could not start: {}".format(error.strerror or error), 0.0)
        guard = awake_guard(process.pid) if keep_awake == CAFFEINATE else None
        if guard is not None:
            guarding.callback(release_guard, guard)
        stdout, errors = process.communicate()
    seconds = time.monotonic() - started
    return ChildRun(process.returncode, stdout or b"", None, seconds, errors or b"")


def awake_guard(pid: int) -> Optional["subprocess.Popen[bytes]"]:
    try:
        return subprocess.Popen(
            [CAFFEINATE, "-i", "-w", str(pid)],
            env=noninteractive.environment(os.environ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None


def release_guard(guard: "subprocess.Popen[bytes]") -> None:
    if guard.poll() is None:
        guard.send_signal(signal.SIGTERM)
    guard.wait()


def model_usage(call: Call) -> List[Tuple[str, Any]]:
    usage = call.envelope.get("modelUsage") if call.envelope is not None else None
    return list(usage.items()) if isinstance(usage, dict) else []


def cost_of(entry: Any) -> Optional[float]:
    cost = entry.get("costUSD") if isinstance(entry, dict) else None
    return cost if is_number(cost) else None


def model_costs(calls: Tuple[Call, ...]) -> ModelCosts:
    entries = [(model, cost_of(entry)) for call in calls for model, entry in model_usage(call)]
    priced = [(model, cost) for model, cost in entries if cost is not None]
    cost = {model: sum(amount for name, amount in priced if name == model) for model, _ in priced}
    unpriced = tuple(dict.fromkeys(model for model, amount in entries if amount is None))
    return ModelCosts(cost, unpriced)


def child_minutes(child: ChildRun, output: Optional[Dict[str, Any]]) -> float:
    duration = output.get("duration_ms") if output is not None else None
    return round(duration / 60000 if is_number(duration) else child.seconds / 60, 3)


def call_record(call: Call) -> Dict[str, Any]:
    return {
        "session_id": call.envelope[child_reply.SESSION_ID] if call.envelope is not None else None,
        "minutes": child_minutes(call.run, call.envelope),
        "exit": call.run.exit,
    }


def background_priority() -> Optional[bool]:
    if sys.platform != "darwin":
        return None
    try:
        return os.getpriority(DARWIN_PROCESS_SELECTOR, 0) == 1
    except OSError:
        return None


def priority() -> Dict[str, Any]:
    return {"nice": os.getpriority(os.PRIO_PROCESS, 0), "background": background_priority()}


def child_record(calls: Tuple[Call, ...], costs: ModelCosts, keep_awake: str) -> Dict[str, Any]:
    recorded = [call_record(call) for call in calls]
    return {
        "session_id": recorded[0]["session_id"],
        "cost": costs.cost,
        "unpriced": list(costs.unpriced),
        "minutes": round(sum(entry["minutes"] for entry in recorded), 3),
        "exit": recorded[-1]["exit"],
        "calls": recorded,
        "keep_awake": keep_awake,
        "priority": priority(),
    }


def blocked_text(reason: str) -> str:
    _, line, _ = verdict.blocked_line(child_reply.one_line(reason))
    return line or ""


def write_json(path: str, value: Dict[str, Any]) -> None:
    write_text(path, json.dumps(value, indent=2) + "\n")


def write_text(path: str, text: str) -> None:
    try:
        write_atomically(path, text)
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(path, error.strerror or error))


def write_bytes(path: str, data: bytes) -> None:
    descriptor, staging = tempfile.mkstemp(prefix="." + os.path.basename(path) + "-", dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(staging, path)
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(path, error.strerror or error))
    finally:
        if os.path.exists(staging):
            os.remove(staging)
