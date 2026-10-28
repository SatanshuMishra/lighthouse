import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from lighthouse_tool import limits, metrics_writer, results as run_files, run_record, suite, verdict, wait
from lighthouse_tool import repo as repository
from lighthouse_tool.records import is_number, write_atomically
from lighthouse_tool.repo import Parser, Refusal, require_root, toplevel

Outcome = Tuple[int, Optional[str], Optional[str]]
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
WORK = "work"
CHILD = "child.json"
LAUNCH = "launch.json"
EARLIER_RUN_FILES = (LAUNCH, CHILD, run_files.LIMITS, *run_record.RESULTS_SOURCES)
FEATURE_PROFILE = ".lighthouse/profile.json"
CAFFEINATE = "caffeinate"
SYSTEMD_INHIBIT = "systemd-inhibit"
NO_KEEP_AWAKE = "none"
DARWIN_PROCESS_SELECTOR = 4
KEEP_AWAKE_GRACE_SECONDS = 5
PATH_FLAGS = ("repo", "results", "previous", "spec")
CHILD_STORE = "plugin-metrics"


class ChildRun(NamedTuple):
    exit: Optional[int]
    stdout: str
    problem: Optional[str]
    seconds: float


def parser() -> Parser:
    arguments = Parser(prog="lighthouse launch", add_help=False)
    for flag in ("--repo", "--core", "--feature", "--results"):
        arguments.add_argument(flag, required=True)
    arguments.add_argument("--previous")
    arguments.add_argument("--spec")
    arguments.add_argument("--parent")
    arguments.add_argument("--final", action="store_true")
    return arguments


def located_parser() -> Parser:
    arguments = Parser(prog="lighthouse launch", add_help=False)
    for flag in ("--repo", "--core", "--feature", "--results", "--previous", "--spec", "--parent"):
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
    found = write_limits(results, feature_profile(root, options.feature))
    keep_awake = keep_awake_tool()
    child = run_child(child_command(options), work, keep_awake, child_environment(results), found.child_seconds)
    output = parsed_output(child.stdout)
    record = child_record(child, output, keep_awake)
    write_json(os.path.join(results, CHILD), record)
    line = verdict_text(output) if child.problem is None else None
    reason = None if line is not None else blocked_reason(child, output)
    printed = line if line is not None else blocked_text(reason)
    warnings = run_record.finished(recording, results, run_record.Ending(printed, reason, child.exit, record["session_id"]))
    try:
        write_text(os.path.join(results, LAUNCH), printed + "\n")
    except Refusal as problem:
        return refused(results, str(problem), warnings)
    summary = "lighthouse launch: the child exited {}".format(child.exit)
    told = summary if reason is None else "{}; blocked: {}".format(summary, reason)
    return 0, printed, with_warnings(told, warnings)


def feature_profile(root: str, feature: str) -> Dict[str, Any]:
    commit = repository.resolve_branch(root, feature)
    if commit is None:
        return {}
    code, stdout, _ = repository.git(root, ["show", "{}:{}".format(commit, FEATURE_PROFILE)])
    if code != 0:
        return {}
    try:
        profile = json.loads(stdout)
    except ValueError:
        return {}
    return profile if isinstance(profile, dict) else {}


def write_limits(results: str, profile: Dict[str, Any]) -> limits.Limits:
    found = limits.of(profile)
    written = {
        **found._asdict(),
        "deadline": time.time() + found.run_seconds,
        "measured": isinstance(profile.get("measured"), dict),
    }
    write_json(os.path.join(results, run_files.LIMITS), written)
    return found


def child_environment(results: str) -> Dict[str, str]:
    return {**run_record.environment_without_parent(), metrics_writer.ROOT_VARIABLE: os.path.join(results, CHILD_STORE)}


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
        )
        if value is not None
    ]
    quoted = [part for flag, value in named for part in (flag, shlex.quote(value))]
    return quoted + (["--final"] if options.final else [])


def child_command(options: argparse.Namespace) -> List[str]:
    return [
        "claude",
        "-p",
        " ".join(["/lighthouse:test", "--child", *test_flags(options)]),
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


def run_child(
    command: List[str], work: str, keep_awake: str, environment: Dict[str, str], limit_seconds: float
) -> ChildRun:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            wrapped(command, keep_awake),
            cwd=work,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        return ChildRun(None, "", "the child session could not start: {}".format(error.strerror or error), 0.0)
    guard = awake_guard(process.pid) if keep_awake == CAFFEINATE else None
    try:
        stdout, _ = process.communicate(timeout=limit_seconds)
        problem = None
    except subprocess.TimeoutExpired:
        stdout = stopped_output(process)
        problem = "the child session ran past its time limit of {:g} seconds".format(limit_seconds)
    seconds = time.monotonic() - started
    if guard is not None:
        release_guard(guard)
    exit_status = process.returncode if problem is None else None
    return ChildRun(exit_status, stdout.decode("utf-8", errors="replace"), problem, seconds)


def stopped_output(process: "subprocess.Popen[bytes]") -> bytes:
    wait.stop_group(process)
    try:
        stdout, _ = process.communicate(timeout=KEEP_AWAKE_GRACE_SECONDS)
    except subprocess.TimeoutExpired as late:
        return late.output or b""
    return stdout or b""


def awake_guard(pid: int) -> Optional["subprocess.Popen[bytes]"]:
    try:
        return subprocess.Popen(
            [CAFFEINATE, "-i", "-w", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None


def release_guard(guard: "subprocess.Popen[bytes]") -> None:
    try:
        guard.wait(timeout=KEEP_AWAKE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        guard.kill()
        guard.wait()


def parsed_output(stdout: str) -> Optional[Dict[str, Any]]:
    try:
        output = json.loads(stdout)
    except ValueError:
        return None
    return output if isinstance(output, dict) else None


def model_costs(output: Optional[Dict[str, Any]]) -> Dict[str, float]:
    usage = output.get("modelUsage") if output is not None else None
    if not isinstance(usage, dict):
        return {}
    return {
        model: entry["costUSD"]
        for model, entry in usage.items()
        if isinstance(entry, dict) and is_number(entry.get("costUSD"))
    }


def child_minutes(child: ChildRun, output: Optional[Dict[str, Any]]) -> float:
    duration = output.get("duration_ms") if output is not None else None
    return round(duration / 60000 if is_number(duration) else child.seconds / 60, 3)


def background_priority() -> Optional[bool]:
    if sys.platform != "darwin":
        return None
    try:
        return os.getpriority(DARWIN_PROCESS_SELECTOR, 0) == 1
    except OSError:
        return None


def priority() -> Dict[str, Any]:
    return {"nice": os.getpriority(os.PRIO_PROCESS, 0), "background": background_priority()}


def child_record(child: ChildRun, output: Optional[Dict[str, Any]], keep_awake: str) -> Dict[str, Any]:
    session = output.get("session_id") if output is not None else None
    return {
        "session_id": session if isinstance(session, str) else None,
        "cost": model_costs(output),
        "minutes": child_minutes(child, output),
        "exit": child.exit,
        "keep_awake": keep_awake,
        "priority": priority(),
    }


def verdict_text(output: Optional[Dict[str, Any]]) -> Optional[str]:
    result = output.get("result") if output is not None else None
    if not isinstance(result, str):
        return None
    lines = [text.strip() for text in result.splitlines()]
    found = [text for text in lines if is_verdict_line(text)]
    return found[-1] if found else None


def is_verdict_line(text: str) -> bool:
    try:
        line = json.loads(text)
    except ValueError:
        return False
    return isinstance(line, dict) and "verdict" in line


def blocked_reason(child: ChildRun, output: Optional[Dict[str, Any]]) -> str:
    if child.problem is not None:
        return child.problem
    if output is None:
        return "the child session exited {} and its output is not JSON".format(child.exit)
    return "the child session exited {} without a verdict line".format(child.exit)


def blocked_text(reason: str) -> str:
    _, line, _ = verdict.blocked_line(reason)
    return line or ""


def write_json(path: str, value: Dict[str, Any]) -> None:
    write_text(path, json.dumps(value, indent=2) + "\n")


def write_text(path: str, text: str) -> None:
    try:
        write_atomically(path, text)
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(path, error.strerror or error))
