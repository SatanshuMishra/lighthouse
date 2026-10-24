import json
import os
import signal
import subprocess
import time
from typing import Any, List, Optional, Tuple

from lighthouse_tool.repo import Parser, Refusal

DEFAULT_EVERY_SECONDS = 5.0
LONGEST_WITHIN_SECONDS = 540.0


def parser() -> Parser:
    arguments = Parser(prog="lighthouse wait", add_help=False)
    arguments.add_argument("--until", required=True)
    arguments.add_argument("--every", type=float, default=DEFAULT_EVERY_SECONDS)
    arguments.add_argument("--within", type=float, default=LONGEST_WITHIN_SECONDS)
    return arguments


def checked_options(options: Any) -> Any:
    if not options.every > 0:
        raise Refusal("--every must be a positive number of seconds")
    if not 0 < options.within <= LONGEST_WITHIN_SECONDS:
        raise Refusal("--within must be a positive number of seconds no more than {:g}".format(LONGEST_WITHIN_SECONDS))
    return options


def check_passes(check: str, seconds_left: float) -> bool:
    process = subprocess.Popen(
        ["/bin/sh", "-c", check],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        return process.wait(timeout=seconds_left) == 0
    except subprocess.TimeoutExpired:
        stop_group(process)
        return False


def stop_group(process: "subprocess.Popen[bytes]") -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        pass
    process.wait()


def wait_until(check: str, every: float, within: float) -> Tuple[bool, float]:
    started = time.monotonic()
    deadline = started + within
    while True:
        seconds_left = deadline - time.monotonic()
        if seconds_left <= 0:
            return False, time.monotonic() - started
        if check_passes(check, seconds_left):
            return True, time.monotonic() - started
        time.sleep(max(0.0, min(every, deadline - time.monotonic())))


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = checked_options(parser().parse_args(argv[1:]))
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse wait: {}".format(refusal)
    ready, seconds = wait_until(options.until, options.every, options.within)
    return 0, json.dumps({"ready": ready, "seconds": round(seconds, 3)}), None
