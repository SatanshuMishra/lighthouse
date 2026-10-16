import importlib
import json
import os
import sys
from typing import List, Optional, Tuple

Outcome = Tuple[int, Optional[str], Optional[str]]

COMMANDS = {
    "change": "change",
    "profile": "profile",
    "readiness": "readiness",
    "answer": "readiness",
    "credentials": "credentials",
    "with-credentials": "credentials",
    "worktrees": "suite",
    "suite": "suite",
    "release": "suite",
    "verdict": "verdict",
    "pr": "pr",
    "spend": "spend",
}

SUBCOMMANDS = sorted([*COMMANDS, "version"])

PLUGIN_MANIFEST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
    ".claude-plugin",
    "plugin.json",
)


def main(argv: List[str]) -> int:
    code, stdout_text, stderr_text = dispatch(list(argv))
    if stdout_text is not None:
        sys.stdout.write(stdout_text + "\n")
    if stderr_text is not None:
        sys.stderr.write(stderr_text + "\n")
    return code


def dispatch(argv: List[str]) -> Outcome:
    subcommand = argv[0] if argv else None
    if subcommand == "version":
        return version()
    if subcommand not in COMMANDS:
        return usage(subcommand)
    module_name = "lighthouse_tool." + COMMANDS[subcommand]
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        return (
            2,
            json.dumps({"error": "subcommand unavailable", "subcommand": subcommand}),
            "lighthouse {}: its module {} cannot be imported: {}".format(subcommand, module_name, error),
        )
    return module.run(argv)


def usage(subcommand: Optional[str]) -> Outcome:
    reason = "no subcommand given" if subcommand is None else "unknown subcommand {}".format(subcommand)
    return (
        2,
        json.dumps({"error": reason, "subcommands": SUBCOMMANDS}),
        "lighthouse: {}; usage: lighthouse <subcommand> [flags]; subcommands: {}".format(
            reason, ", ".join(SUBCOMMANDS)
        ),
    )


def version() -> Outcome:
    try:
        with open(PLUGIN_MANIFEST, encoding="utf-8") as manifest:
            plugin_version = json.load(manifest)["version"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        return (
            2,
            json.dumps({"error": "plugin manifest unreadable"}),
            "lighthouse version: cannot read {}: {}".format(PLUGIN_MANIFEST, error),
        )
    return 0, json.dumps({"version": plugin_version}), None
