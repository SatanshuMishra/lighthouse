import argparse
import json
import os
import stat
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool import repo as repository

Outcome = Tuple[int, Optional[str], Optional[str]]
Problem = Dict[str, Optional[str]]

FILE_NAME = "credentials.env"
SHARED_MODE_BITS = stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH
REFUSING_KINDS = ("missing-file", "mode", "not-ignored", "production")
QUOTES = ("'", '"')


class Refusal(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Refusal(message)


def credentials_parser() -> Parser:
    arguments = Parser(prog="lighthouse credentials", add_help=False)
    arguments.add_argument("action", choices=["init", "check"])
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--profile")
    return arguments


def with_credentials_parser() -> Parser:
    arguments = Parser(prog="lighthouse with-credentials", add_help=False)
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--profile")
    arguments.add_argument("--cwd")
    return arguments


def run(argv: List[str]) -> Outcome:
    subcommand = argv[0] if argv else "credentials"
    try:
        if subcommand == "with-credentials":
            return with_credentials(argv[1:])
        return credentials(argv[1:])
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse {}: {}".format(subcommand, refusal)


def credentials(arguments: List[str]) -> Outcome:
    options = credentials_parser().parse_args(arguments)
    root, profile = located(options.repo, options.profile)
    if options.action == "init":
        return init(root, profile)
    return check(root, profile)


def located(repo: str, profile_path: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    root = repository.toplevel(repo)
    if root is None:
        raise Refusal("{} is not a git repository".format(repo))
    profile = repository.load_profile(root, profile_path)
    if not isinstance(profile, dict):
        raise Refusal("no readable profile; run lighthouse:init to write .lighthouse/profile.json")
    if credentials_path(root, profile) is None:
        raise Refusal("cannot locate the credentials file for {}".format(repo))
    return root, profile


def credentials_section(profile: Dict[str, Any]) -> Dict[str, Any]:
    section = profile.get("credentials")
    return section if isinstance(section, dict) else {}


def project_file(profile: Dict[str, Any]) -> Optional[str]:
    named = credentials_section(profile).get("file")
    return named if isinstance(named, str) and named else None


def credentials_path(repo: str, profile: Dict[str, Any]) -> Optional[str]:
    named = project_file(profile)
    if named is not None:
        root = repository.toplevel(repo)
        return os.path.join(root, named) if root else None
    folder = repository.state_dir(repo)
    return os.path.join(folder, FILE_NAME) if folder else None


def production_names(profile: Dict[str, Any]) -> List[str]:
    names = credentials_section(profile).get("names")
    entries = names if isinstance(names, dict) else {}
    return [name for name, entry in entries.items() if isinstance(entry, dict) and entry.get("production") is True]


def needed_names(profile: Dict[str, Any]) -> List[str]:
    names = credentials_section(profile).get("names")
    declared = list(names) if isinstance(names, dict) else []
    surfaces = profile.get("surfaces")
    surface_names = [
        name
        for surface in (surfaces if isinstance(surfaces, list) else [])
        if isinstance(surface, dict) and isinstance(surface.get("credentials"), list)
        for name in surface["credentials"]
        if isinstance(name, str)
    ]
    return list(dict.fromkeys([*declared, *surface_names]))


def unquoted(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in QUOTES:
        return value[1:-1]
    return value


def parsed_line(line: str) -> Optional[Tuple[str, str]]:
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        return None
    name, value = text.split("=", 1)
    return name.strip(), unquoted(value.strip())


def read_entries(path: str) -> Dict[str, str]:
    try:
        with open(path, encoding="utf-8") as credentials_file:
            lines = credentials_file.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    pairs = [pair for pair in (parsed_line(line) for line in lines) if pair is not None]
    return dict(pairs)


def file_mode(path: str) -> Optional[int]:
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return None


def is_ignored(root: str, path: str) -> bool:
    code, _, _ = repository.git(root, ["check-ignore", "-q", "--", path])
    return code == 0


def file_problems(repo: str, profile: Dict[str, Any]) -> List[Problem]:
    path = credentials_path(repo, profile)
    if path is None:
        return [{"kind": "missing-file", "name": None}]
    mode = file_mode(path)
    root = repository.toplevel(repo) or repo
    file_level = [
        *([{"kind": "missing-file", "name": None}] if mode is None else []),
        *([{"kind": "mode", "name": None}] if mode is not None and mode & SHARED_MODE_BITS else []),
        *([{"kind": "not-ignored", "name": None}] if project_file(profile) and not is_ignored(root, path) else []),
    ]
    entries = read_entries(path) if mode is not None else {}
    name_level = [
        {"kind": "missing" if name not in entries else "empty", "name": name}
        for name in needed_names(profile)
        if not entries.get(name)
    ]
    production = [{"kind": "production", "name": name} for name in production_names(profile) if entries.get(name)]
    return [*file_level, *name_level, *production]


def reason(problem: Problem, path: str) -> str:
    kind, name = problem["kind"], problem["name"]
    if kind == "missing-file":
        return "{} does not exist; run lighthouse credentials init".format(path)
    if kind == "mode":
        return "{} has mode {:04o}, so group or others can read or write it; run chmod 600 on it".format(
            path, file_mode(path) or 0
        )
    if kind == "not-ignored":
        return "{} is not ignored by git, so it could be committed".format(path)
    if kind == "missing":
        return "{} is absent from {}".format(name, path)
    if kind == "empty":
        return "{} has an empty value in {}".format(name, path)
    return "{} is marked production in the profile and has a value in {}".format(name, path)


def init(root: str, profile: Dict[str, Any]) -> Outcome:
    if project_file(profile) is not None:
        path = credentials_path(root, profile)
        return 0, json.dumps({"file": path, "created": False, "added": [], "project_file": True}), None
    folder = repository.ensure_state_dir(root)
    if folder is None:
        raise Refusal("cannot create the state folder for {}".format(root))
    path = os.path.join(folder, FILE_NAME)
    created = not os.path.exists(path)
    if created:
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        os.chmod(path, 0o600)
    present = read_entries(path)
    added = [name for name in needed_names(profile) if name not in present]
    if added:
        append_names(path, added)
    return 0, json.dumps({"file": path, "created": created, "added": added, "project_file": False}), None


def append_names(path: str, names: List[str]) -> None:
    with open(path, encoding="utf-8") as credentials_file:
        existing = credentials_file.read()
    separator = "\n" if existing and not existing.endswith("\n") else ""
    with open(path, "a", encoding="utf-8") as credentials_file:
        credentials_file.write(separator + "".join("{}=\n".format(name) for name in names))


def check(root: str, profile: Dict[str, Any]) -> Outcome:
    path = credentials_path(root, profile) or ""
    problems = file_problems(root, profile)
    report = json.dumps({"file": path, "ok": not problems, "problems": problems})
    if not problems:
        return 0, report, None
    reasons = "\n".join("lighthouse credentials check: {}".format(reason(problem, path)) for problem in problems)
    return 1, report, reasons


def split_command(arguments: List[str]) -> Tuple[List[str], List[str]]:
    if "--" not in arguments:
        raise Refusal("usage: lighthouse with-credentials --repo <repo> [--profile <path>] [--cwd <dir>] -- <command...>")
    boundary = arguments.index("--")
    return arguments[:boundary], arguments[boundary + 1 :]


def redacted(text: str, filled: Dict[str, str]) -> str:
    ordered = sorted(filled.items(), key=lambda item: len(item[1]), reverse=True)
    result = text
    for name, value in ordered:
        result = result.replace(value, "[redacted:{}]".format(name))
    return result


def passed_on(text: str, filled: Dict[str, str]) -> Optional[str]:
    clean = redacted(text, filled)
    trimmed = clean[:-1] if clean.endswith("\n") else clean
    return trimmed if clean else None


def with_credentials(arguments: List[str]) -> Outcome:
    flags, command = split_command(arguments)
    options = with_credentials_parser().parse_args(flags)
    if not command:
        raise Refusal("no command given after --")
    root, profile = located(options.repo, options.profile)
    path = credentials_path(root, profile) or ""
    refusing = [problem for problem in file_problems(root, profile) if problem["kind"] in REFUSING_KINDS]
    if refusing:
        reasons = [reason(problem, path) for problem in refusing]
        return (
            2,
            json.dumps({"error": "refused, running nothing", "file": path, "problems": refusing}),
            "\n".join("lighthouse with-credentials: refused, running nothing: {}".format(text) for text in reasons),
        )
    entries = read_entries(path)
    filled = {name: value for name, value in entries.items() if value}
    try:
        completed = subprocess.run(
            command,
            cwd=options.cwd or root,
            env={**os.environ, **filled},
            capture_output=True,
            text=True,
            errors="replace",
        )
    except OSError as error:
        message = redacted("cannot run {}: {}".format(command[0], error.strerror or error), filled)
        return 2, json.dumps({"error": message}), "lighthouse with-credentials: {}".format(message)
    code = completed.returncode if completed.returncode >= 0 else 128 - completed.returncode
    return code, passed_on(completed.stdout, filled), passed_on(completed.stderr, filled)
