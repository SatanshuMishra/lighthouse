import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from lighthouse_tool import suite, verdict
from lighthouse_tool.repo import Parser, Refusal, repository_folder, require_root

Outcome = Tuple[int, Optional[str], Optional[str]]
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
WORK = "work"
CHILD = "child.json"
LAUNCH = "launch.json"
CAFFEINATE = "caffeinate"
SYSTEMD_INHIBIT = "systemd-inhibit"
NO_KEEP_AWAKE = "none"
DARWIN_PROCESS_SELECTOR = 4
KEEP_AWAKE_GRACE_SECONDS = 5
PATH_FLAGS = ("repo", "results", "previous", "spec")


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
    arguments.add_argument("--final", action="store_true")
    return arguments


def run(argv: List[str]) -> Outcome:
    try:
        options = parser().parse_args(argv[1:])
        return launch(options)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse launch: {}".format(refusal)


def launch(options: argparse.Namespace) -> Outcome:
    root = require_root(options.repo)
    if suite.is_inside(root, options.results):
        raise Refusal(
            "the results folder {} is inside the repository {}; choose a folder outside it".format(options.results, root)
        )
    work = os.path.join(os.path.abspath(options.results), WORK)
    os.makedirs(work, exist_ok=True)
    results = os.path.realpath(options.results)
    keep_awake = keep_awake_tool()
    child = run_child(child_command(options), work, keep_awake)
    output = parsed_output(child.stdout)
    record = child_record(child, output, keep_awake)
    write_json(os.path.join(results, CHILD), record)
    line = verdict_text(output)
    reason = None if line is not None else blocked_reason(child, output)
    printed = line if line is not None else blocked_text(reason)
    write_text(os.path.join(results, LAUNCH), printed + "\n")
    verdict.append_ledger(root, launch_record(root, results, record, json.loads(printed)["verdict"], reason))
    summary = "lighthouse launch: the child exited {}".format(child.exit)
    return 0, printed, summary if reason is None else "{}; blocked: {}".format(summary, reason)


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


def run_child(command: List[str], work: str, keep_awake: str) -> ChildRun:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            wrapped(command, keep_awake),
            cwd=work,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        return ChildRun(None, "", "the child session could not start: {}".format(error.strerror or error), 0.0)
    guard = awake_guard(process.pid) if keep_awake == CAFFEINATE else None
    stdout, _ = process.communicate()
    seconds = time.monotonic() - started
    if guard is not None:
        release_guard(guard)
    return ChildRun(process.returncode, stdout.decode("utf-8", errors="replace"), None, seconds)


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


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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


def launch_record(
    root: str, results: str, record: Dict[str, Any], outcome: str, reason: Optional[str]
) -> Dict[str, Any]:
    return {
        "run": results,
        "kind": "launch",
        "time": verdict.utc_now(),
        "repo": repository_folder(root),
        "cost": record["cost"],
        "minutes": record["minutes"],
        "keep_awake": record["keep_awake"],
        "priority": record["priority"],
        "verdict": outcome,
        "reason": reason,
    }


def write_json(path: str, value: Dict[str, Any]) -> None:
    write_text(path, json.dumps(value, indent=2) + "\n")


def write_text(path: str, text: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(path, error.strerror or error))
