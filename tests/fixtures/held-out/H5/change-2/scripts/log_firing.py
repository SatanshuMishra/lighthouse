import json
import os
import sys
from datetime import datetime, timezone


def log_path():
    return os.environ.get("KILNMATE_LOG") or os.path.join(os.path.expanduser("~"), ".kilnmate", "firings.jsonl")


def logged_count(path):
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def main():
    try:
        schedule = json.loads(sys.stdin.read())
    except ValueError:
        print("log_firing: standard input does not hold one JSON schedule", file=sys.stderr)
        return 1
    path = log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    number = logged_count(path) + 1
    entry = {"firing": number, "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **schedule}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    print("Firing {}: {} to cone {}".format(number, schedule["glaze"], schedule["cone"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
