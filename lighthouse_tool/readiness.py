import json
import os
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool import credentials
from lighthouse_tool import profile as profiles
from lighthouse_tool import repo as repository
from lighthouse_tool.repo import Parser, Refusal, require_root

Outcome = Tuple[int, Optional[str], Optional[str]]
Item = Dict[str, Optional[str]]

UNREADABLE_PROFILE_KINDS = ("missing", "malformed")
UNFILLED_CREDENTIAL_KINDS = ("missing", "empty")


def readiness_parser() -> Parser:
    arguments = Parser(prog="lighthouse readiness", add_help=False)
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--profile")
    return arguments


def answer_parser() -> Parser:
    arguments = Parser(prog="lighthouse answer", add_help=False)
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--set", action="append", required=True, dest="settings")
    arguments.add_argument("--profile")
    return arguments


def run(argv: List[str]) -> Outcome:
    subcommand = argv[0] if argv else "readiness"
    try:
        if subcommand == "answer":
            return answer(argv[1:])
        return readiness(argv[1:])
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse {}: {}".format(subcommand, refusal)


def profile_path_option(path: Optional[str]) -> Optional[str]:
    return os.path.abspath(path) if path else None


def readable_profile(root: str, path: Optional[str]) -> Optional[Dict[str, Any]]:
    problems = profiles.check_profile(root, path)
    if any(found["kind"] in UNREADABLE_PROFILE_KINDS for found in problems):
        return None
    loaded = repository.load_profile(root, path)
    return loaded if isinstance(loaded, dict) else None


def item(kind: str, name: Optional[str], question: str, file: Optional[str] = None) -> Item:
    return {"kind": kind, "name": name, "question": question, "file": file}


def fact_items(profile: Dict[str, Any], answers: Dict[str, Any]) -> List[Item]:
    facts = profile.get("facts")
    entries = facts if isinstance(facts, dict) else {}
    return [
        item("fact", name, "What is {}? {}".format(name, recheck_of(fact)).strip())
        for name, fact in entries.items()
        if isinstance(fact, dict) and fact.get("confirmed") is not True and name not in answers
    ]


def recheck_of(fact: Dict[str, Any]) -> str:
    recheck = fact.get("recheck")
    return recheck if isinstance(recheck, str) else ""


def credential_items(root: str, profile: Dict[str, Any]) -> List[Item]:
    path = credentials.credentials_path(root, profile)
    unfilled = [
        found["name"]
        for found in credentials.file_problems(root, profile)
        if found["kind"] in UNFILLED_CREDENTIAL_KINDS and found["name"]
    ]
    return [item("credential", name, "Fill {} in {}".format(name, path), path) for name in unfilled]


def open_items(root: str, path: Optional[str]) -> List[Item]:
    profile = readable_profile(root, path)
    if profile is None:
        return [item("profile", None, "Run lighthouse:init to write the profile.")]
    return [*fact_items(profile, repository.read_answers(root)), *credential_items(root, profile)]


def readiness(arguments: List[str]) -> Outcome:
    options = readiness_parser().parse_args(arguments)
    root = require_root(options.repo)
    found = open_items(root, profile_path_option(options.profile))
    report = json.dumps({"ready": not found, "open": found})
    reasons = "\n".join("lighthouse readiness: open: {}".format(entry["question"]) for entry in found)
    return 0, report, reasons or None


def parsed_setting(setting: str) -> Tuple[str, str]:
    if "=" not in setting:
        raise Refusal("--set {} is not <fact>=<value>".format(setting))
    name, value = setting.split("=", 1)
    if not name:
        raise Refusal("--set {} names no fact".format(setting))
    return name, value


def parsed_value(text: str) -> Any:
    try:
        parsed = json.loads(text)
    except ValueError:
        return text
    return parsed if json.dumps(parsed) == text else text


def needed_credential_names(root: str, path: Optional[str]) -> List[str]:
    profile = repository.load_profile(root, path)
    return credentials.credential_names(profile) if isinstance(profile, dict) else []


def credential_refusal(root: str, profile: Dict[str, Any], name: str) -> str:
    where = credentials.credentials_path(root, profile) or "the credentials file"
    return "{} is a credential name; credentials go in {}, never in an answer".format(name, where)


def answer(arguments: List[str]) -> Outcome:
    options = answer_parser().parse_args(arguments)
    root = require_root(options.repo)
    path = profile_path_option(options.profile)
    settings = [parsed_setting(setting) for setting in options.settings]
    secret_names = set(needed_credential_names(root, path))
    refused = next((name for name, _ in settings if name in secret_names), None)
    if refused is not None:
        raise Refusal(credential_refusal(root, repository.load_profile(root, path), refused))
    folder = repository.ensure_state_dir(root)
    if folder is None:
        raise Refusal("cannot create the state folder for {}".format(root))
    new_answers = {name: parsed_value(value) for name, value in settings}
    repository.write_answers(folder, {**repository.read_answers(root), **new_answers})
    return 0, json.dumps({"stored": list(new_answers)}), None

