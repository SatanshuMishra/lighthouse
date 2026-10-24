import datetime
import json
import os
import tempfile
from typing import Any, Dict, List, Optional

PRIVATE_FILE = 0o600


class UnreadableLine(ValueError):
    def __init__(self, path: str, number: int) -> None:
        super().__init__("{} line {} is not a JSON object".format(path, number))


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def json_object(text: str) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_json_lines(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as handle:
            text_lines = handle.read().splitlines()
    except FileNotFoundError:
        return []
    numbered = [(number, text) for number, text in enumerate(text_lines, start=1) if text.strip()]
    parsed = [(number, json_object(text)) for number, text in numbered]
    unreadable = [number for number, line in parsed if line is None]
    if unreadable:
        raise UnreadableLine(path, unreadable[0])
    return [line for _, line in parsed if line is not None]


def append_json_line(path: str, record: Dict[str, Any], mode: int) -> None:
    descriptor = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, mode)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        separator = "" if ends_with_newline(descriptor) else "\n"
        handle.write(separator + json.dumps(record) + "\n")


def ends_with_newline(descriptor: int) -> bool:
    size = os.fstat(descriptor).st_size
    return size == 0 or os.pread(descriptor, 1, size - 1) == b"\n"


def write_atomically(path: str, text: str) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    descriptor, staging = tempfile.mkstemp(prefix="." + os.path.basename(path) + "-", dir=folder)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(staging, path)
    except OSError:
        if os.path.exists(staging):
            os.remove(staging)
        raise
