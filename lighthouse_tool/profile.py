import fnmatch
import json
import os
import posixpath
import re
import shlex
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple

from lighthouse_tool import repo as repository
from lighthouse_tool import suite
from lighthouse_tool.records import is_number
from lighthouse_tool.repo import Parser, Refusal, checked_git, require_root

Outcome = Tuple[int, Optional[str], Optional[str]]
Problem = Dict[str, str]

PROFILE_PATH = ".lighthouse/profile.json"
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "profile_schema.json")
PUBLISH_MESSAGE = "chore(lighthouse): record the test profile"
UPGRADED_SUITE_KEYS = ("rerun", "isolated")

SOURCE_NAMES = (
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements*.txt",
    "Pipfile",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Package.swift",
    "pubspec.yaml",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "tox.ini",
    "pytest.ini",
    "noxfile.py",
    "playwright.config.*",
    "jest.config.*",
    "vitest.config.*",
    "cypress.config.*",
    "*.csproj",
    ".gitlab-ci.yml",
)
SOURCE_PATHS = (".claude-plugin/plugin.json",)
WORKFLOW_FOLDER = ".github/workflows"
WORKFLOW_SUFFIXES = (".yml", ".yaml")

SEGMENT_SEPARATORS = frozenset(["&&", "||", ";", ";;", "|", "|&", "&"])
GROUPING_TOKENS = frozenset(["(", ")", "((", "))"])
SHELL_BUILTINS = frozenset(
    [
        ":", ".", "[", "alias", "bg", "break", "cd", "command", "continue", "declare", "echo", "eval", "exec", "exit",
        "export", "false", "fc", "fg", "getopts", "hash", "jobs", "kill", "local", "newgrp", "printf", "pwd", "read",
        "readonly", "return", "set", "shift", "source", "test", "times", "trap", "true", "type", "typeset", "ulimit",
        "umask", "unalias", "unset", "wait",
    ]
)
LEADING_KEYWORDS = frozenset(["{", "!", "if", "then", "else", "elif", "while", "until", "do", "time"])
PROGRAMLESS_KEYWORDS = frozenset(["}", "fi", "done", "esac", "for", "case", "select", "function"])
LITERAL_DIRECTORY = re.compile(r"^[A-Za-z0-9_./-]+$")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
GLOB_MARKERS = ("*", "?", "[", "...")
SCRIPT_SUFFIXES = (".sh", ".py", ".js", ".mjs", ".ts", ".rb", ".pl")

InterpreterOptions = Tuple[frozenset, frozenset]

PYTHON_OPTIONS = (frozenset(["-W", "-X", "--check-hash-based-pycs"]), frozenset(["-m", "-c"]))
SHELL_OPTIONS = (frozenset(["-o", "-O", "--rcfile", "--init-file"]), frozenset(["-c"]))
NODE_OPTIONS = (
    frozenset(["-r", "--require", "--import", "--loader", "--experimental-loader", "--input-type", "-C", "--conditions", "--env-file"]),
    frozenset(["-e", "--eval", "-p", "--print"]),
)
RUBY_OPTIONS = (frozenset(["-r", "-I", "-E", "-C"]), frozenset(["-e"]))
PERL_OPTIONS = (frozenset(["-I", "-M", "-m"]), frozenset(["-e", "-E"]))

INTERPRETERS: Dict[str, InterpreterOptions] = {
    "sh": SHELL_OPTIONS,
    "bash": SHELL_OPTIONS,
    "zsh": SHELL_OPTIONS,
    "python": PYTHON_OPTIONS,
    "python3": PYTHON_OPTIONS,
    "node": NODE_OPTIONS,
    "ruby": RUBY_OPTIONS,
    "perl": PERL_OPTIONS,
}


def check_parser() -> Parser:
    arguments = Parser(prog="lighthouse profile check", add_help=False)
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--profile")
    return arguments


def publish_parser() -> Parser:
    arguments = Parser(prog="lighthouse profile publish", add_help=False)
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--feature", required=True)
    arguments.add_argument("--profile")
    return arguments


def run(argv: List[str]) -> Outcome:
    action = argv[1] if len(argv) > 1 else None
    handlers: Dict[str, Callable[[List[str]], Outcome]] = {"check": check_command, "publish": publish_command}
    if action not in handlers:
        reason = "no action given" if action is None else "unknown action {}".format(action)
        return (
            2,
            json.dumps({"error": reason, "actions": sorted(handlers)}),
            "lighthouse profile: {}; usage: lighthouse profile check|publish --repo <repo>".format(reason),
        )
    try:
        return handlers[action](argv[2:])
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse profile {}: {}".format(action, refusal)


def check_command(args: List[str]) -> Outcome:
    options = check_parser().parse_args(args)
    root = require_root(options.repo)
    profile_path = os.path.abspath(options.profile) if options.profile else None
    problems = check_profile(root, profile_path)
    upgrades = check_upgrades(root, profile_path)
    if not problems:
        return 0, json.dumps({"ok": True, "problems": [], "upgrades": upgrades}), None
    reasons = ["lighthouse profile check: {}: {}".format(item["kind"], item["detail"]) for item in problems]
    return 1, json.dumps({"ok": False, "problems": problems, "upgrades": upgrades}), "\n".join(reasons)


def problem(kind: str, detail: str) -> Problem:
    return {"kind": kind, "detail": detail}


def upgrade(field: str) -> Problem:
    return {"field": field, "detail": "{} is not set, and lighthouse:doctor writes it".format(field)}


def check_upgrades(repo: str, path: Optional[str] = None) -> List[Problem]:
    suite = section(repository.load_profile(repo, path), "suite")
    if not suite:
        return []
    return [upgrade("suite." + key) for key in UPGRADED_SUITE_KEYS if key not in suite]


def load_schema() -> Dict[str, Any]:
    with open(SCHEMA_PATH, encoding="utf-8") as schema_file:
        return json.load(schema_file)


def check_profile(repo: str, path: Optional[str] = None) -> List[Problem]:
    root = repository.toplevel(repo) or os.path.realpath(repo)
    profile_path = path or os.path.join(root, PROFILE_PATH)
    if not os.path.isfile(profile_path):
        return [problem("missing", "{} does not exist".format(profile_path))]
    try:
        with open(profile_path, encoding="utf-8") as profile_file:
            profile = json.load(profile_file)
    except ValueError as error:
        return [problem("malformed", "{} is not valid JSON: {}".format(profile_path, error))]
    except OSError as error:
        return [problem("malformed", "{} cannot be read: {}".format(profile_path, error))]
    schema = load_schema()
    if not isinstance(profile, dict):
        return [problem("schema", "the profile must be a JSON object")]
    version = profile.get("version")
    if not (is_integer(version) and version == schema["version"]):
        return [problem("version", "version is {}, and this lighthouse reads version {}".format(json.dumps(version), schema["version"]))]
    return [
        *schema_problems(profile, schema["profile"], ""),
        *path_problems(root, profile),
        *command_problems(root, profile),
        *rerun_problems(profile),
        *unrecorded_problems(root, profile),
    ]


def rerun_problems(profile: Dict[str, Any]) -> List[Problem]:
    rerun = section(profile, "suite").get("rerun")
    quoted = suite.quoted_placeholders(rerun) if isinstance(rerun, str) else []
    if not quoted:
        return []
    detail = "suite.rerun puts {} inside quotes; leave each placeholder an unquoted word, because lighthouse quotes every value itself"
    return [problem("rerun", detail.format(", ".join(quoted)))]


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


TYPE_TESTS: Dict[str, Callable[[Any], bool]] = {
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: isinstance(value, bool),
    "integer": is_integer,
    "number": is_number,
    "null": lambda value: value is None,
    "object": lambda value: isinstance(value, dict),
    "map": lambda value: isinstance(value, dict),
    "list": lambda value: isinstance(value, list),
    "any": lambda value: True,
}


def key_path(where: str, key: str) -> str:
    return "{}.{}".format(where, key) if where else key


def schema_problems(value: Any, node: Dict[str, Any], where: str) -> List[Problem]:
    types = node["type"] if isinstance(node["type"], list) else [node["type"]]
    if not any(TYPE_TESTS[name](value) for name in types):
        return [problem("schema", "{} must be {}".format(where or "the profile", " or ".join(types)))]
    if "enum" in node and value not in node["enum"]:
        allowed = ", ".join(json.dumps(item) for item in node["enum"])
        return [problem("schema", "{} is {}, and must be one of {}".format(where, json.dumps(value), allowed))]
    if "minimum" in node and is_number(value) and value < node["minimum"]:
        return [problem("schema", "{} is {}, and must be at least {}".format(where, value, node["minimum"]))]
    if isinstance(value, list) and "items" in node:
        return [
            found
            for index, item in enumerate(value)
            for found in schema_problems(item, node["items"], "{}[{}]".format(where, index))
        ]
    if isinstance(value, dict) and "values" in node:
        return [
            found
            for name, item in value.items()
            for found in schema_problems(item, node["values"], key_path(where, name))
        ]
    if isinstance(value, dict) and ("required" in node or "optional" in node):
        return object_problems(value, node, where)
    return []


def object_problems(value: Dict[str, Any], node: Dict[str, Any], where: str) -> List[Problem]:
    required = node.get("required", {})
    optional = node.get("optional", {})
    known = {**required, **optional}
    missing = [
        problem("schema", "{} is required and missing".format(key_path(where, key)))
        for key in required
        if key not in value
    ]
    unknown = [
        problem("schema", "{} is not a key the profile schema defines".format(key_path(where, key)))
        for key in value
        if key not in known
    ]
    nested = [
        found
        for key, child in known.items()
        if key in value
        for found in schema_problems(value[key], child, key_path(where, key))
    ]
    return [*missing, *unknown, *nested]


def section(container: Any, key: str) -> Dict[str, Any]:
    value = container.get(key) if isinstance(container, dict) else None
    return value if isinstance(value, dict) else {}


def strings(value: Any) -> List[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def surfaces(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    value = profile.get("surfaces")
    return [surface for surface in value if isinstance(surface, dict)] if isinstance(value, list) else []


def unique(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))


def recorded_paths(profile: Dict[str, Any]) -> List[str]:
    surface_paths = [path for surface in surfaces(profile) for path in strings(surface.get("paths"))]
    return unique([*strings(profile.get("sources")), *surface_paths])


def recorded_commands(profile: Dict[str, Any]) -> List[str]:
    commands = [
        section(profile, "setup").get("command"),
        section(profile, "suite").get("command"),
        section(profile, "build").get("command"),
        section(profile, "start").get("command"),
        *[section(surface, "sign_in").get("command") for surface in surfaces(profile)],
    ]
    return unique([command for command in commands if isinstance(command, str)])


def inside_repository(path: str) -> bool:
    normal = posixpath.normpath(path)
    return bool(path) and not posixpath.isabs(normal) and normal != ".." and not normal.startswith("../")


def path_problems(root: str, profile: Dict[str, Any]) -> List[Problem]:
    faults = [(path, path_fault(root, path)) for path in recorded_paths(profile)]
    return [problem("path", "{} {}".format(path, fault)) for path, fault in faults if fault]


def path_fault(root: str, path: str) -> Optional[str]:
    if not inside_repository(path):
        return "is not a repository-relative path"
    if not os.path.exists(os.path.join(root, path)):
        return "does not exist in the repository"
    return None


def command_problems(root: str, profile: Dict[str, Any]) -> List[Problem]:
    faults = [(command, command_fault(root, command)) for command in recorded_commands(profile)]
    return [
        problem("command", "{} does not resolve: {}".format(command, fault))
        for command, fault in faults
        if fault
    ]


def tokens_of(command: str) -> List[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def is_redirection(token: str) -> bool:
    return bool(token) and set(token) <= set("<>&|") and ("<" in token or ">" in token)


def segments_of(tokens: List[str]) -> List[List[str]]:
    segments: List[List[str]] = [[]]
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
        elif token in SEGMENT_SEPARATORS:
            segments = [*segments, []]
        elif is_redirection(token):
            skip_next = True
        elif token not in GROUPING_TOKENS:
            segments = [*segments[:-1], [*segments[-1], token]]
    return [segment for segment in segments if segment]


def command_fault(root: str, command: str) -> Optional[str]:
    try:
        tokens = tokens_of(command)
    except ValueError as error:
        return "it cannot be parsed: {}".format(error)
    programs = [words for words in (program_words(segment) for segment in segments_of(tokens)) if words]
    if not programs:
        return "it names no program"
    folders: Optional[List[str]] = [root]
    for segment in programs:
        fault = segment_fault(folders, segment[0], segment[1:]) if folders is not None else None
        if fault:
            return fault
        if segment[0] == "cd" and folders is not None:
            folders = folders_after_cd(root, folders, segment[1:])
    return None


def program_words(segment: List[str]) -> List[str]:
    start = 0
    while start < len(segment) and (ASSIGNMENT.match(segment[start]) or segment[start] in LEADING_KEYWORDS):
        start += 1
    words = segment[start:]
    return [] if words and words[0] in PROGRAMLESS_KEYWORDS else words


def folders_after_cd(root: str, folders: List[str], arguments: List[str]) -> Optional[List[str]]:
    if len(arguments) != 1 or not LITERAL_DIRECTORY.match(arguments[0]):
        return None
    target = arguments[0]
    entered = [os.path.normpath(os.path.join(folder, target)) for folder in folders]
    return unique([*folders, *[folder for folder in entered if is_within(root, folder)]])


def is_within(root: str, folder: str) -> bool:
    return os.path.commonpath([root, folder]) == root


def exists_in_any(folders: List[str], path: str) -> bool:
    return any(os.path.exists(os.path.join(folder, path)) for folder in folders)


def segment_fault(folders: List[str], program: str, arguments: List[str]) -> Optional[str]:
    if not program_resolves(folders, program):
        return "program {} is not a shell builtin, not on PATH and not an existing path".format(program)
    options = INTERPRETERS.get(posixpath.basename(program))
    script = script_argument(arguments, options) if options else None
    if script is not None and looks_like_script(script) and not exists_in_any(folders, script):
        return "script {} does not exist in the repository".format(script)
    return None


def program_resolves(folders: List[str], program: str) -> bool:
    if "/" in program:
        return exists_in_any(folders, program)
    return program in SHELL_BUILTINS or shutil.which(program) is not None or exists_in_any(folders, program)


def script_argument(arguments: List[str], options: InterpreterOptions) -> Optional[str]:
    value_options, scriptless_options = options
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            return arguments[index + 1] if index + 1 < len(arguments) else None
        if argument == "-":
            return None
        if not argument.startswith("-"):
            return argument
        if argument.startswith("--"):
            name = argument.split("=", 1)[0]
            if name in scriptless_options:
                return None
            index += 2 if name in value_options and "=" not in argument else 1
            continue
        consumed = short_options_consumed(argument, value_options, scriptless_options)
        if consumed is None:
            return None
        index += consumed
    return None


def short_options_consumed(argument: str, value_options: frozenset, scriptless_options: frozenset) -> Optional[int]:
    letters = argument[1:]
    for position, letter in enumerate(letters):
        flag = "-" + letter
        if flag in scriptless_options:
            return None
        if flag in value_options:
            return 2 if position == len(letters) - 1 else 1
    return 1


def looks_like_script(argument: str) -> bool:
    if any(marker in argument for marker in GLOB_MARKERS):
        return False
    return argument.endswith(SCRIPT_SUFFIXES) or "/" in argument


def tracked_files(root: str) -> List[str]:
    code, stdout, _ = repository.git(root, ["ls-files", "-z"])
    if code != 0:
        return []
    return [path for path in stdout.split("\0") if path and not path.startswith(".lighthouse/")]


def is_source(path: str) -> bool:
    name = posixpath.basename(path)
    return (
        any(fnmatch.fnmatchcase(name, pattern) for pattern in SOURCE_NAMES)
        or path in SOURCE_PATHS
        or (posixpath.dirname(path) == WORKFLOW_FOLDER and path.endswith(WORKFLOW_SUFFIXES))
    )


def unrecorded_problems(root: str, profile: Dict[str, Any]) -> List[Problem]:
    recorded = {posixpath.normpath(path) for path in strings(profile.get("sources"))}
    return [
        problem("unrecorded", "{} is a manifest, CI or test configuration the profile's sources do not list".format(path))
        for path in tracked_files(root)
        if is_source(path) and posixpath.normpath(path) not in recorded
    ]


def fold_answers(profile: Dict[str, Any], answers: Dict[str, Any]) -> Dict[str, Any]:
    facts = profile.get("facts")
    if not isinstance(facts, dict):
        return dict(profile)
    folded = {
        name: {**fact, "value": answers[name], "confirmed": True} if name in answers and isinstance(fact, dict) else fact
        for name, fact in facts.items()
    }
    return {**profile, "facts": folded}


def publish_command(args: List[str]) -> Outcome:
    options = publish_parser().parse_args(args)
    root = require_root(options.repo)
    profile = repository.load_profile(root, os.path.abspath(options.profile) if options.profile else None)
    if not isinstance(profile, dict):
        raise Refusal("there is no readable profile at {}".format(options.profile or os.path.join(root, PROFILE_PATH)))
    folded = fold_answers(profile, repository.read_answers(root))
    commit = repository.resolve_branch(root, options.feature)
    if commit is None:
        raise Refusal("branch {} does not exist locally or on origin".format(options.feature))
    return 0, json.dumps(publish(root, options.feature, commit, folded)), None


def publish(root: str, feature: str, commit: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    holder = tempfile.mkdtemp(prefix="lighthouse-publish-")
    worktree = os.path.join(holder, "feature")
    try:
        checked_git(root, ["worktree", "add", "--quiet", "--detach", worktree, commit])
        return commit_profile(root, worktree, feature, commit, profile)
    finally:
        repository.git(root, ["worktree", "remove", "--force", worktree])
        repository.git(root, ["worktree", "prune"])
        shutil.rmtree(holder, ignore_errors=True)


def commit_profile(root: str, worktree: str, feature: str, commit: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    target = os.path.join(worktree, PROFILE_PATH)
    linked = [path for path in (os.path.dirname(target), target) if os.path.islink(path)]
    if linked:
        raise Refusal(
            "{} on {} is a symbolic link, so lighthouse will not write through it".format(
                os.path.relpath(linked[0], worktree), feature
            )
        )
    os.makedirs(os.path.dirname(target), exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as profile_file:
        profile_file.write(json.dumps(profile, indent=2) + "\n")
    if not checked_git(worktree, ["status", "--porcelain", "--", PROFILE_PATH]).strip():
        return {"committed": False}
    has_origin = repository.has_origin(root)
    holders = [] if has_origin else branch_holders(root, feature)
    if holders:
        raise Refusal(
            "{} is checked out in {} and there is no origin to push to, so lighthouse will not move it".format(
                feature, ", ".join(holders)
            )
        )
    checked_git(worktree, ["add", "--force", "--", PROFILE_PATH])
    checked_git(worktree, ["commit", "--quiet", "-m", PUBLISH_MESSAGE, "--", PROFILE_PATH])
    published = checked_git(worktree, ["rev-parse", "HEAD"]).strip()
    if has_origin:
        checked_git(worktree, ["push", "--quiet", "origin", "HEAD:refs/heads/" + feature])
    else:
        checked_git(root, ["update-ref", "refs/heads/" + feature, published, commit])
    return {"committed": True, "commit": published}


def branch_holders(root: str, feature: str) -> List[str]:
    listing = checked_git(root, ["worktree", "list", "--porcelain"])
    blocks = [block.splitlines() for block in listing.strip().split("\n\n") if block.strip()]
    wanted = "branch refs/heads/" + feature
    return [
        block[0][len("worktree "):]
        for block in blocks
        if block and block[0].startswith("worktree ") and wanted in block
    ]
