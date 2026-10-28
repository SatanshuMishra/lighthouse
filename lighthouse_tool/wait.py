import http.client
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from lighthouse_tool import process_tree
from lighthouse_tool.ports import port_map, port_pair, url_with_build_ports, with_build_ports
from lighthouse_tool.records import is_number
from lighthouse_tool.repo import Parser, Refusal, read_json_or_refuse

DEFAULT_EVERY_SECONDS = 5.0
LONGEST_WITHIN_SECONDS = 540.0
READY_KINDS = ("url", "line", "command")
URL_SCHEMES = ("http", "https")
FIRST_FAILING_STATUS = 400
LAST_CONTROL_CHARACTER = 0x20
DELETE_CHARACTER = 0x7F
UNREQUESTABLE_URL = "start.ready is not an http or https URL lighthouse can request; fix it in the profile, or wait with --ready line or --ready command"

Check = Callable[[float], bool]


def parser() -> Parser:
    arguments = Parser(prog="lighthouse wait", add_help=False)
    arguments.add_argument("--until")
    arguments.add_argument("--ready", choices=READY_KINDS)
    arguments.add_argument("--profile")
    arguments.add_argument("--log")
    arguments.add_argument("--port", type=port_pair, action="append")
    arguments.add_argument("--every", type=float, default=DEFAULT_EVERY_SECONDS)
    arguments.add_argument("--within", type=float, default=LONGEST_WITHIN_SECONDS)
    arguments.add_argument("--limits")
    return arguments


def checked_options(options: Any) -> Any:
    if (options.until is None) == (options.ready is None):
        raise Refusal("give either --until <check> or --ready url|line|command with --profile <file>")
    if options.ready is not None and options.profile is None:
        raise Refusal("--ready reads start.ready from the profile; give --profile <file>")
    if options.ready is None and options.port:
        raise Refusal("--port rewrites the profile's start.ready; give it with --ready")
    if options.ready == "line" and options.log is None:
        raise Refusal("--ready line searches the start log; give --log <file>")
    if not options.every > 0:
        raise Refusal("--every must be a positive number of seconds")
    if not 0 < options.within <= LONGEST_WITHIN_SECONDS:
        raise Refusal("--within must be a positive number of seconds no more than {:g}".format(LONGEST_WITHIN_SECONDS))
    return options


def ready_text(profile_path: str) -> str:
    profile = read_json_or_refuse(profile_path)
    start = profile.get("start") if isinstance(profile, dict) else None
    ready = start.get("ready") if isinstance(start, dict) else None
    if not isinstance(ready, str) or not ready.strip():
        raise Refusal("{} has no start.ready to wait for".format(profile_path))
    return ready


def is_control(character: str) -> bool:
    return ord(character) <= LAST_CONTROL_CHARACTER or ord(character) == DELETE_CHARACTER


def requestable(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
        return (
            parts.scheme in URL_SCHEMES
            and bool(parts.hostname)
            and parts.port != 0
            and bool(parts.hostname.encode("idna"))
        )
    except (ValueError, UnicodeError):
        return False


def checked_url(ready: str) -> str:
    url = ready.strip()
    if any(is_control(character) for character in url) or not requestable(url):
        raise Refusal(UNREQUESTABLE_URL)
    return urllib.parse.urlsplit(url).geturl()


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
    except http.client.InvalidURL:
        raise Refusal(UNREQUESTABLE_URL)
    except (OSError, ValueError, http.client.HTTPException):
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
    ports = port_map(options.port)
    if options.ready == "url":
        url = checked_url(url_with_build_ports(checked_url(ready), ports))
        return lambda seconds_left: url_answers(url, seconds_left)
    build_ready = with_build_ports(ready, ports)
    if options.ready == "line":
        return lambda _: log_holds(options.log, build_ready)
    return lambda seconds_left: check_passes(build_ready, seconds_left)


def check_passes(check: str, seconds_left: float) -> bool:
    process = process_tree.start(
        ["/bin/sh", "-c", check],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with process_tree.owned(process):
        try:
            return process.wait(timeout=seconds_left) == 0
        except subprocess.TimeoutExpired:
            return False


def never_ends() -> bool:
    return False


def wait_until(
    check: Check, every: float, within: float, ended: Callable[[], bool] = never_ends
) -> Tuple[bool, float]:
    started = time.monotonic()
    deadline = started + within
    while True:
        seconds_left = deadline - time.monotonic()
        if seconds_left <= 0 or ended():
            return False, time.monotonic() - started
        if check(seconds_left):
            return True, time.monotonic() - started
        time.sleep(max(0.0, min(every, deadline - time.monotonic())))


def limits_deadline(path: str) -> Optional[float]:
    try:
        with open(path, encoding="utf-8") as handle:
            written = json.load(handle)
    except (OSError, ValueError):
        return None
    deadline = written.get("deadline") if isinstance(written, dict) else None
    return deadline if is_number(deadline) else None


def is_expired(path: str, deadline: Optional[float]) -> bool:
    return not os.path.exists(path) or (deadline is not None and time.time() >= deadline)


def window(within: float, deadline: Optional[float]) -> float:
    return within if deadline is None else min(within, deadline - time.time())


def bounded_wait(check: Check, options: Any) -> Dict[str, Any]:
    deadline = limits_deadline(options.limits)
    if deadline is not None and time.time() >= deadline:
        return {"ready": False, "seconds": 0, "expired": True}
    ready, seconds = wait_until(check, options.every, window(options.within, deadline))
    expired = not ready and is_expired(options.limits, limits_deadline(options.limits))
    return {"ready": ready, "seconds": round(seconds, 3), "expired": expired}


def waited(check: Check, options: Any) -> Dict[str, Any]:
    if options.limits is not None:
        return bounded_wait(check, options)
    ready, seconds = wait_until(check, options.every, options.within)
    return {"ready": ready, "seconds": round(seconds, 3)}


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = checked_options(parser().parse_args(argv[1:]))
        check = ready_check(options)
        result = waited(check, options)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse wait: {}".format(refusal)
    return 0, json.dumps(result), None
