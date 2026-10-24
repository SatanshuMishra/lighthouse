import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, List, Optional, Tuple

from lighthouse_tool.repo import Parser, Refusal, load_profile

DEFAULT_EVERY_SECONDS = 5.0
LONGEST_WITHIN_SECONDS = 540.0
READY_KINDS = ("url", "line", "command")
URL_SCHEMES = ("http", "https")
FIRST_FAILING_STATUS = 400

Check = Callable[[float], bool]


def parser() -> Parser:
    arguments = Parser(prog="lighthouse wait", add_help=False)
    arguments.add_argument("--until")
    arguments.add_argument("--ready", choices=READY_KINDS)
    arguments.add_argument("--profile")
    arguments.add_argument("--log")
    arguments.add_argument("--every", type=float, default=DEFAULT_EVERY_SECONDS)
    arguments.add_argument("--within", type=float, default=LONGEST_WITHIN_SECONDS)
    return arguments


def checked_options(options: Any) -> Any:
    if (options.until is None) == (options.ready is None):
        raise Refusal("give either --until <check> or --ready url|line|command with --profile <file>")
    if options.ready is not None and options.profile is None:
        raise Refusal("--ready reads start.ready from the profile; give --profile <file>")
    if options.ready == "line" and options.log is None:
        raise Refusal("--ready line searches the start log; give --log <file>")
    if not options.every > 0:
        raise Refusal("--every must be a positive number of seconds")
    if not 0 < options.within <= LONGEST_WITHIN_SECONDS:
        raise Refusal("--within must be a positive number of seconds no more than {:g}".format(LONGEST_WITHIN_SECONDS))
    return options


def ready_text(profile_path: str) -> str:
    profile = load_profile(profile_path, profile_path)
    start = profile.get("start") if isinstance(profile, dict) else None
    ready = start.get("ready") if isinstance(start, dict) else None
    if not isinstance(ready, str) or not ready.strip():
        raise Refusal("{} has no start.ready to wait for".format(profile_path))
    return ready


def checked_url(ready: str) -> str:
    parts = urllib.parse.urlsplit(ready.strip())
    if parts.scheme not in URL_SCHEMES or not parts.netloc:
        raise Refusal("start.ready is not an http or https URL; wait with --ready line or --ready command")
    return parts.geturl()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *arguments: Any) -> None:
        return None


def url_answers(url: str, seconds_left: float) -> bool:
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url, timeout=seconds_left) as response:
            return response.status < FIRST_FAILING_STATUS
    except urllib.error.HTTPError as answer:
        return answer.code < FIRST_FAILING_STATUS
    except (OSError, ValueError):
        return False


def log_holds(log: str, line: str) -> bool:
    try:
        with open(log, encoding="utf-8", errors="replace") as handle:
            return line in handle.read()
    except OSError:
        return False


def ready_check(options: Any) -> Check:
    if options.ready is None:
        return lambda seconds_left: check_passes(options.until, seconds_left)
    ready = ready_text(options.profile)
    if options.ready == "url":
        url = checked_url(ready)
        return lambda seconds_left: url_answers(url, seconds_left)
    if options.ready == "line":
        return lambda _: log_holds(options.log, ready)
    return lambda seconds_left: check_passes(ready, seconds_left)


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


def wait_until(check: Check, every: float, within: float) -> Tuple[bool, float]:
    started = time.monotonic()
    deadline = started + within
    while True:
        seconds_left = deadline - time.monotonic()
        if seconds_left <= 0:
            return False, time.monotonic() - started
        if check(seconds_left):
            return True, time.monotonic() - started
        time.sleep(max(0.0, min(every, deadline - time.monotonic())))


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = checked_options(parser().parse_args(argv[1:]))
        check = ready_check(options)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse wait: {}".format(refusal)
    ready, seconds = wait_until(check, options.every, options.within)
    return 0, json.dumps({"ready": ready, "seconds": round(seconds, 3)}), None
