import http.client
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from lighthouse_tool import process_tree
from lighthouse_tool.ports import port_map, port_pair, url_with_build_ports, with_build_ports
from lighthouse_tool.repo import Parser, Refusal, read_json_or_refuse

DEFAULT_EVERY_SECONDS = 5.0
ATTEMPT_SECONDS = 60
READY_KINDS = ("url", "line", "command")
URL_SCHEMES = ("http", "https")
FIRST_FAILING_STATUS = 400
LAST_CONTROL_CHARACTER = 0x20
DELETE_CHARACTER = 0x7F
EXIT_STATUS = re.compile(r"-?[0-9]{1,10}")
UNREQUESTABLE_URL = "start.ready is not an http or https URL lighthouse can request; fix it in the profile, or wait with --ready line or --ready command"

Check = Callable[[], bool]


def parser() -> Parser:
    arguments = Parser(prog="lighthouse wait", add_help=False)
    arguments.add_argument("--until")
    arguments.add_argument("--ready", choices=READY_KINDS)
    arguments.add_argument("--profile")
    arguments.add_argument("--log")
    arguments.add_argument("--port", type=port_pair, action="append")
    arguments.add_argument("--every", type=float, default=DEFAULT_EVERY_SECONDS)
    arguments.add_argument("--exit-file", required=True)
    return arguments


def checked_options(options: Any) -> Any:
    if not options.exit_file.strip():
        raise Refusal("--exit-file names the file the awaited process writes its exit status to; give a path")
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


def url_answers(url: str) -> bool:
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url, timeout=ATTEMPT_SECONDS) as response:
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
        return lambda: check_passes(options.until)
    ready = ready_text(options.profile)
    ports = port_map(options.port)
    if options.ready == "url":
        url = checked_url(url_with_build_ports(checked_url(ready), ports))
        return lambda: url_answers(url)
    build_ready = with_build_ports(ready, ports)
    if options.ready == "line":
        return lambda: log_holds(options.log, build_ready)
    return lambda: check_passes(build_ready)


def check_passes(check: str) -> bool:
    with process_tree.started(
        ["/bin/sh", "-c", check],
        0.0,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as process:
        return process.wait() == 0


def wait_until(check: Check, every: float, ended: Callable[[], bool]) -> Tuple[bool, float]:
    started = time.monotonic()
    while True:
        if ended():
            return False, time.monotonic() - started
        if check():
            return True, time.monotonic() - started
        time.sleep(every)


def exit_status(path: str) -> Optional[int]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read().strip()
    except OSError:
        return None
    return int(text) if EXIT_STATUS.fullmatch(text) else None


def waited(check: Check, options: Any) -> Dict[str, Any]:
    exit_file = options.exit_file
    ready, seconds = wait_until(check, options.every, lambda: os.path.exists(exit_file))
    if ready:
        return {"ready": True, "exited": False, "seconds": round(seconds, 3)}
    return {"ready": False, "exited": True, "status": exit_status(exit_file), "seconds": round(seconds, 3)}


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = checked_options(parser().parse_args(argv[1:]))
        check = ready_check(options)
        result = waited(check, options)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse wait: {}".format(refusal)
    return 0, json.dumps(result), None
