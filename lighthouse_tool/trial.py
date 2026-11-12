import json
import os
import subprocess
from contextlib import ExitStack, contextmanager
from typing import IO, Any, Dict, Iterator, List, Mapping, Optional, Tuple

from lighthouse_tool import process_tree
from lighthouse_tool.repo import Parser, Refusal, read_json_or_refuse

MANIFEST = os.path.join(".claude-plugin", "plugin.json")
CONFIG_VARIABLE = "CLAUDE_CONFIG_DIR"
CONFIG_DEFAULT = os.path.join("~", ".claude")
PLUGIN_CACHE = os.path.join("plugins", "cache")
INSTALLED = os.path.join("plugins", "installed_plugins.json")
CACHE_VARIABLE = "CLAUDE_CODE_PROMPT_CACHE_TTL"
CACHE_LIFETIME = "5m"
EFFORT_VARIABLE = "CLAUDE_CODE_EFFORT_LEVEL"
DEFAULT_MODEL = "opus"
DEFAULT_EFFORT = "high"
SOURCES_OF_THE_FOLDER = "project,local"
OWNED_FLAGS = ("-p", "--print", "--plugin-dir", "--settings", "--setting-sources", "--output-format", "--model", "--effort")
SEPARATOR = "--"
STOP_GRACE_SECONDS = 0.0
ANOTHER_COPY = "a session loaded another copy of the plugin, or none: its transcript is not a trial of this build"
FAILED_SESSION = "a session exited with a status other than 0"
Session = Tuple[ExitStack, "subprocess.Popen[bytes]"]


def parser() -> Parser:
    arguments = Parser(prog="lighthouse trial", add_help=False)
    arguments.add_argument("--plugin-dir", required=True)
    arguments.add_argument("--request", required=True)
    arguments.add_argument("--evidence", required=True)
    arguments.add_argument("--name", required=True)
    arguments.add_argument("--folder", action="append", required=True)
    arguments.add_argument("--model", default=DEFAULT_MODEL)
    arguments.add_argument("--effort", default=DEFAULT_EFFORT)
    return arguments


def parsed(words: List[str]) -> Tuple[Any, List[str]]:
    own = words[: words.index(SEPARATOR)] if SEPARATOR in words else words
    return parser().parse_args(own), words[len(own) + 1 :]


def config_folder(environment: Mapping[str, str]) -> str:
    return environment.get(CONFIG_VARIABLE) or os.path.expanduser(CONFIG_DEFAULT)


def plugin_name(build: str) -> str:
    manifest = read_json_or_refuse(os.path.join(build, MANIFEST))
    name = manifest.get("name") if isinstance(manifest, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise Refusal("{} names no plugin".format(os.path.join(build, MANIFEST)))
    return name


def installed_copies(config: str, name: str) -> List[str]:
    record_path = os.path.join(config, INSTALLED)
    if not os.path.exists(record_path):
        return []
    record = read_json_or_refuse(record_path)
    plugins = record.get("plugins") if isinstance(record, dict) else None
    if not isinstance(plugins, dict):
        raise Refusal("{} holds no plugins table".format(record_path))
    return sorted(key for key in plugins if key.partition("@")[0] == name)


def same_file(one: str, other: str) -> bool:
    try:
        return os.path.samefile(one, other)
    except (OSError, ValueError):
        return False


def ancestors(path: str) -> Iterator[str]:
    parent = os.path.dirname(path)
    yield path
    while parent != path:
        path, parent = parent, os.path.dirname(parent)
        yield path


def inside(folder: str, entry: str) -> bool:
    return bool(entry) and any(same_file(folder, ancestor) for ancestor in ancestors(os.path.realpath(entry)))


def search_path(inherited: str, config: str) -> str:
    cache = os.path.join(config, PLUGIN_CACHE)
    return os.pathsep.join(entry for entry in inherited.split(os.pathsep) if not inside(cache, entry))


def session_environment(inherited: Mapping[str, str], config: str) -> Dict[str, str]:
    kept = {name: value for name, value in inherited.items() if name != EFFORT_VARIABLE}
    return {**kept, "PATH": search_path(inherited.get("PATH", os.defpath), config), CACHE_VARIABLE: CACHE_LIFETIME}


def session_argv(options: Any, passed_on: List[str], build: str, disabled: List[str]) -> List[str]:
    settings = ["--settings", json.dumps({"enabledPlugins": {key: False for key in disabled}})] if disabled else []
    return [
        "claude", "-p", options.request, "--plugin-dir", build, "--setting-sources", SOURCES_OF_THE_FOLDER, *settings,
        "--output-format", "stream-json", "--verbose", "--model", options.model, "--effort", options.effort,
        *passed_on,
    ]


def identity(folder: str) -> Tuple[int, int]:
    found = os.stat(folder)
    return found.st_dev, found.st_ino


def checked(options: Any, passed_on: List[str]) -> Tuple[str, List[str], str]:
    given = (options.request, options.name, options.model, options.effort, options.evidence, options.plugin_dir, *options.folder)
    if any(not isinstance(value, str) or value == SEPARATOR for value in given):
        raise Refusal("{} is no value for a flag".format(SEPARATOR))
    if not options.request.strip():
        raise Refusal("--request needs the words a person would send")
    if options.request.startswith("-"):
        raise Refusal("--request begins with a dash, which claude would read as a flag of its own")
    if options.name != os.path.basename(options.name) or options.name in ("", ".", ".."):
        raise Refusal("--name is one file name, the stem of each transcript")
    owned = [flag for flag in passed_on if flag.partition("=")[0] in OWNED_FLAGS]
    if owned:
        raise Refusal("{} is set by lighthouse trial itself".format(owned[0]))
    folders = [os.path.realpath(folder) for folder in options.folder]
    for folder in folders:
        if not os.path.isdir(folder):
            raise Refusal("{} is not a folder: prepare each trial's folder first".format(folder))
    if len({identity(folder) for folder in folders}) != len(folders):
        raise Refusal("each trial needs a folder of its own")
    build = os.path.realpath(options.plugin_dir)
    return build, folders, os.path.realpath(options.evidence)


def trial_files(evidence: str, name: str, count: int) -> List[Tuple[str, str]]:
    return [(os.path.join(evidence, "{}-{}.jsonl".format(name, number)), os.path.join(evidence, "{}-{}.stderr".format(name, number))) for number in range(1, count + 1)]


def removed(paths: List[str]) -> None:
    for path in paths:
        os.remove(path)


def unwritable(path: str, error: OSError) -> Refusal:
    if isinstance(error, FileExistsError):
        return Refusal("{} exists: a trial never overwrites evidence, so give this set another --name".format(path))
    return Refusal("cannot write {}: {}".format(path, error.strerror or error))


@contextmanager
def created(files: List[Tuple[str, str]]) -> Iterator[List[Tuple[IO[bytes], IO[bytes]]]]:
    handles: List[IO[bytes]] = []
    try:
        for path in [path for pair in files for path in pair]:
            try:
                handles.append(open(path, "xb"))
            except OSError as error:
                removed([handle.name for handle in handles])
                raise unwritable(path, error)
        yield list(zip(handles[0::2], handles[1::2]))
    finally:
        for handle in handles:
            handle.close()


def loaded_copies(transcript: str, name: str) -> List[str]:
    with open(transcript, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "system" and event.get("subtype") == "init":
                plugins = event.get("plugins")
                rows = plugins if isinstance(plugins, list) else []
                return [str(row.get("path")) for row in rows if isinstance(row, dict) and row.get("name") == name]
    return []


def started(
    owning: ExitStack, argv: List[str], number: int, folder: str, outputs: Tuple[IO[bytes], IO[bytes]], environment: Dict[str, str]
) -> Session:
    transcript, errors = outputs
    own = owning.enter_context(ExitStack())
    try:
        return own, own.enter_context(
            process_tree.started(argv, STOP_GRACE_SECONDS, cwd=folder, env=environment, stdin=subprocess.DEVNULL, stdout=transcript, stderr=errors)
        )
    except OSError as error:
        raise Refusal("trial {} cannot start claude in {}: {}".format(number, folder, error.strerror or error))


def ended(session: Session) -> int:
    own, process = session
    code = process.wait()
    own.close()
    return code


def run_sessions(argv: List[str], folders: List[str], files: List[Tuple[str, str]], environment: Dict[str, str]) -> List[int]:
    with ExitStack() as owning:
        outputs = owning.enter_context(created(files))
        owning.enter_context(process_tree.guarded())
        try:
            sessions = [
                started(owning, argv, number, folder, pair, environment) for number, (folder, pair) in enumerate(zip(folders, outputs), start=1)
            ]
            return [ended(session) for session in sessions]
        except BaseException:
            owning.close()
            removed([path for pair in files for path in pair])
            raise


def problem(rows: List[Dict[str, Any]], build: str) -> Optional[str]:
    if any(row["exit"] != 0 for row in rows):
        return FAILED_SESSION
    if any(len(row["loaded"]) != 1 or not same_file(row["loaded"][0], build) for row in rows):
        return ANOTHER_COPY
    return None


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options, passed_on = parsed(argv[1:])
        build, folders, evidence = checked(options, passed_on)
        name = plugin_name(build)
        config = config_folder(os.environ)
        disabled = installed_copies(config, name)
        files = trial_files(evidence, options.name, len(folders))
        os.makedirs(evidence, exist_ok=True)
        exits = run_sessions(session_argv(options, passed_on, build, disabled), folders, files, session_environment(os.environ, config))
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse trial: {}".format(refusal)
    except OSError as error:
        return 2, json.dumps({"error": str(error)}), "lighthouse trial: {}".format(error)
    rows = [
        {"trial": number, "folder": folder, "transcript": transcript, "stderr": errors, "exit": code, "loaded": loaded_copies(transcript, name)}
        for number, (folder, (transcript, errors), code) in enumerate(zip(folders, files, exits), start=1)
    ]
    report = {"plugin": name, "build": build, "disabled": disabled, "model": options.model, "effort": options.effort, "trials": rows}
    error = problem(rows, build)
    if error:
        return 1, json.dumps({**report, "error": error}), "lighthouse trial: {}".format(error)
    return 0, json.dumps(report), None
