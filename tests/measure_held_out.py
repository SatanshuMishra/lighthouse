import argparse
import json
import sys
import unittest
from typing import Any, Dict, List

from tests import e2e_harness

BASELINE_KEYS = ("sessions", "minutes", "dollars", "broken_green", "met", "seed")


def parser() -> argparse.ArgumentParser:
    arguments = argparse.ArgumentParser(prog="python3 -m tests.measure_held_out")
    arguments.add_argument("--plugin-dir", required=True)
    arguments.add_argument("--commit", required=True)
    arguments.add_argument("--out", required=True)
    return arguments


def baseline_record(measured: Dict[str, Any], commit: str) -> Dict[str, Any]:
    return {"commit": commit, **{key: measured[key] for key in BASELINE_KEYS}}


def main(argv: List[str]) -> int:
    options = parser().parse_args(argv)
    holder = unittest.TestCase()
    try:
        measured = e2e_harness.measured_pass(holder, e2e_harness.held_out_cases(), options.plugin_dir)
    finally:
        holder.doCleanups()
    with open(options.out, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(baseline_record(measured, options.commit), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
