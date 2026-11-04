import configparser
import json
import math
import os
import posixpath
import re
import shlex
from typing import Any, Callable, Dict, FrozenSet, List, NamedTuple, Optional, Sequence, Tuple, TypeVar, Union

from lighthouse_tool.profile import (
    INTERPRETERS,
    PROFILE_PATH,
    SHELL_BUILTINS,
    folders_after_cd,
    program_words,
    script_argument,
    segments_of,
    tokens_of,
)


class Finding(NamedTuple):
    runner: str
    file: Optional[str]
    question: str


class _Reach(NamedTuple):
    runner: str
    words: str
    file: Optional[str]
    recognised: bool


class _Place(NamedTuple):
    root: str
    folders: Optional[Tuple[str, ...]]
    file: str
    trail: Tuple[str, ...]
    scripts: FrozenSet[Tuple[str, str]]
    assignments: Tuple[str, ...] = ()


_Runner = Callable[[_Place, List[str]], List[_Reach]]
_Judged = TypeVar("_Judged")

_LAUNCHERS = frozenset(["npx", "bunx"])
_TWO_WORD_LAUNCHERS = frozenset([("pnpm", "exec"), ("yarn", "exec"), ("uv", "run"), ("poetry", "run"), ("pipenv", "run")])
_LOCAL_BINARIES = "node_modules/.bin/"
_PYTHON = re.compile(r"^python(?:\d+(?:\.\d+)?)?$")
_PYTHON_VALUE_OPTIONS = INTERPRETERS["python"][0]
_IMPORT_EXTENSIONS = (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts")
_RELATIVE_SPECIFIER = re.compile(r"""(?:\bfrom|\bimport|\brequire)\s*\(?\s*['"](\.{1,2}/[^'"]+)['"]""")
_QUOTED_TEST_FLAG = re.compile(r"""(['"`])--test\1""")
_SOURCE_TOKEN = re.compile(
    r"""("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`)|//[^\n]*|/\*.*?\*/""", re.DOTALL
)
_KEPT_LITERALS = frozenset(["node:test", "run"])
_BLANK_LITERAL = '""'
_NAME = r"([\w$]+)"
_NODE_TEST = r"""['"`]node:test['"`]"""
_REQUIRED = r"require\(\s*" + _NODE_TEST + r"\s*\)"
_IMPORTED = r"import\(\s*" + _NODE_TEST + r"\s*\)"
_LOADED = r"(?:" + _REQUIRED + r"|(?:await\s+)?" + _IMPORTED + r")"
_RUN_IN_BRACES = r"\{[^{}]*\brun\b[^{}]*\}"
_RUN_MEMBER = r"""\s*(?:\.\s*run\b|\[\s*['"`]run['"`]\s*\])"""
_THEN = r"\s*\.\s*then\(\s*(?:async\s+)?"
_NODE_TEST_BINDINGS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bimport\s+(?:\*\s*as\s+)?" + _NAME + r"\s*(?:,\s*\{[^{}]*\}\s*)?from\s*" + _NODE_TEST,
        r"\bimport\s+" + _NAME + r"\s*=\s*" + _REQUIRED,
        r"\b(?:const|let|var)\s+" + _NAME + r"\s*=\s*" + _LOADED,
        _IMPORTED + _THEN + r"\(?\s*" + _NAME + r"\s*[,)=]",
    )
)
_ALIAS = re.compile(r"\b(?:const|let|var)\s+" + _NAME + r"\s*=\s*(?:await\s+)?" + _NAME + r"\s*(?:;|$)", re.MULTILINE)
_RUN_FROM_NODE_TEST = re.compile(
    _RUN_IN_BRACES + r"\s*(?:from\s*" + _NODE_TEST + r"|=\s*" + _LOADED + r")"
    + r"|" + _IMPORTED + _THEN + r"\(\s*" + _RUN_IN_BRACES
    + r"|(?:" + _REQUIRED + r"|\(\s*await\s+" + _IMPORTED + r"\s*\))" + _RUN_MEMBER
)
_RE_EXPORT_CLAUSE = re.compile(r"""\bexport\s*(?:\*\s*(?:as\s*([\w$]+)\s*)?|(\{[^{}]*\})\s*)from\s*['"`]([^'"`]*)['"`]""")
_IMPORT_CLAUSE = re.compile(r"""\bimport\s*(?:[\w$]+\s*,\s*)?\{([^{}]*)\}\s*from\s*(['"])(\.{1,2}/[^'"]+)\2\s*;?""")
_NAMESPACE_IMPORT = re.compile(r"""\bimport\s*\*\s*as\s*([\w$]+)\s*from\s*(['"])(\.{1,2}/[^'"]+)\2""")
_RELATIVE_SOURCE = re.compile(r"""((?:\bfrom|\bimport|\brequire)\s*\(?\s*)(['"])(\.{1,2}/[^'"]+)\2""")
_TEXT_TEST_TIMEOUT = re.compile(r"""--test-timeout(?:=|['"`]\s*,\s*['"`]?)\s*([0-9][0-9_.eE+]*|Infinity)""")
_RUN_TIMEOUT = re.compile(r"""[{,]\s*timeout\s*:\s*([^,}\s)]+)""")
_NOT_A_BOUND = frozenset(
    [_BLANK_LITERAL, "Infinity", "Number.POSITIVE_INFINITY", "undefined", "null", "number", "string", "any", "unknown", "never", "void"]
)
_ZERO_TEST_TIMEOUT = re.compile(r"""\btestTimeout['"]?\s*:\s*0(?![\w.])""")
_ZERO_TIMEOUT = re.compile(r"""\btimeout\s*:\s*0(?![\w.])""")
_MOCHA_TIMEOUT_OFF = re.compile(r"""\btimeout['"]?\s*[:=]\s*['"]?(?:0|false)(?![\w.])""")
_DART_TIMEOUT_OFF = re.compile(r"""(?m)^\s*timeout\s*:\s*['"]?none['"]?\s*(?:#.*)?$""")
_GO_ZERO_DURATION = re.compile(r"(?:0+(?:\.0*)?(?:ns|us|µs|ms|s|m|h)?)+")
_PYPROJECT_SECTION = "tool.pytest.ini_options"
_PYTEST_CONFIGS = (
    ("pytest.ini", "pytest"),
    ("pyproject.toml", _PYPROJECT_SECTION),
    ("tox.ini", "pytest"),
    ("setup.cfg", "tool:pytest"),
)
_PYTEST_SECTION_BY_EXTENSION = {".toml": _PYPROJECT_SECTION, ".cfg": "tool:pytest"}
_CONFIG_OPTIONS = ("--config", "-c")
_SHORT_OPTION = re.compile(r"-[A-Za-z]")
_NEXTEST_CONFIG = ".config/nextest.toml"
_NEXTEST_PROFILE_VARIABLE = "NEXTEST_PROFILE="
_NEXTEST_DEFAULT_PROFILE = "default"
_NEXTEST_TIMEOUT_KEY = re.compile(r"profile\.([^.]+)\.slow-timeout(\.[^.]+)?")
_NEXTEST_TERMINATE_KEY = ".terminate-after"
_TERMINATE_AFTER = re.compile(r"\bterminate-after\s*=\s*([0-9]+)")
_ANSWER_VALUE = "<where each test is bounded>"


def bound_findings(root: str, command: str) -> Tuple[Finding, ...]:
    real_root = os.path.realpath(root)
    start = _Place(real_root, (real_root,), PROFILE_PATH, (), frozenset())
    return _findings(root, _command_reaches(start, command, ()))


def _findings(root: str, reaches: List[_Reach]) -> Tuple[Finding, ...]:
    runners = _unique([found.runner for found in reaches])
    return tuple(_finding(root, [found for found in reaches if found.runner == runner]) for runner in runners)


def _finding(root: str, group: List[_Reach]) -> Finding:
    runner = group[0].runner
    places = "; ".join(_unique(["{} ({})".format(found.words, found.file) for found in group]))
    answer = "lighthouse answer --repo {} --set {}".format(
        shlex.quote(root), shlex.quote("test-bound:{}={}".format(runner, _ANSWER_VALUE))
    )
    if group[0].recognised:
        question = (
            "The test runner {} does not bound each test in the project's own configuration, reached by {}. "
            "Bound each test there, or record where each test is bounded: {}"
        ).format(runner, places, answer)
    else:
        question = (
            "lighthouse cannot recognise the test runner {}, reached by {}, so it cannot tell whether each test is "
            "bounded. Bound each test in the project's own configuration and record where: {}"
        ).format(runner, places, answer)
    return Finding(runner, group[0].file, question)


def _unique(items: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(items))


def _reach(place: _Place, runner: str, file: Optional[str] = None) -> _Reach:
    return _Reach(runner, ", then ".join(place.trail), file or place.file, True)


def _unrecognised(place: _Place, word: str, file: Optional[str] = None) -> _Reach:
    return _Reach(word, ", then ".join(place.trail), file or place.file, False)


def _command_reaches(place: _Place, command: str, appended: Tuple[str, ...]) -> List[_Reach]:
    try:
        tokens = tokens_of(command)
    except ValueError:
        words = command.split()
        trail = place._replace(trail=(*place.trail, command))
        return [_unrecognised(trail, words[0] if words else command)]
    raw = segments_of(tokens)
    joined = [*raw[:-1], [*raw[-1], *appended]] if raw and appended else raw
    reaches: List[_Reach] = []
    folders = place.folders
    exported = place.assignments
    for segment in joined:
        words = program_words(segment)
        if not words:
            continue
        if words[0] == "export":
            exported = (*exported, *words[1:])
            continue
        if words[0] == "cd":
            entered = folders_after_cd(place.root, list(folders), words[1:]) if folders is not None else None
            folders = tuple(entered) if entered is not None else None
            continue
        if words[0] in SHELL_BUILTINS:
            continue
        prefix = segment[: len(segment) - len(words)]
        here = place._replace(folders=folders, trail=(*place.trail, " ".join(words)), assignments=(*exported, *prefix))
        reaches = [*reaches, *_segment_reaches(here, words)]
    return reaches


def _segment_reaches(place: _Place, words: List[str]) -> List[_Reach]:
    if place.folders is None:
        return [_unrecognised(place, words[0])]
    command = _unwrapped(words)
    if not command:
        return [_unrecognised(place, words[0])]
    if _PYTHON.match(command[0]):
        module = _python_module(command[1:])
        if module is None:
            return [_unrecognised(place, command[0])]
        command = _unwrapped(module)
        if not command:
            return [_unrecognised(place, words[0])]
    runner = _RUNNERS.get(command[0])
    if runner is None:
        return [_unrecognised(place, command[0])]
    return runner(place, command)


def _unwrapped(words: List[str]) -> List[str]:
    if not words:
        return []
    program = words[0]
    if _LOCAL_BINARIES in program:
        return _unwrapped([program.split(_LOCAL_BINARIES)[-1], *words[1:]])
    if program in _LAUNCHERS:
        return _unwrapped(_without_leading_options(words[1:]))
    if tuple(words[:2]) in _TWO_WORD_LAUNCHERS:
        return _unwrapped(_without_leading_options(words[2:]))
    return words


def _without_leading_options(words: List[str]) -> List[str]:
    start = 0
    while start < len(words) and words[start].startswith("-"):
        start += 1
    return words[start:]


def _python_module(arguments: List[str]) -> Optional[List[str]]:
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "-m":
            return arguments[index + 1 :] if index + 1 < len(arguments) else None
        if argument.startswith("-m") and not argument.startswith("--"):
            return [argument[2:], *arguments[index + 1 :]]
        if not argument.startswith("-"):
            return None
        index += 2 if argument in _PYTHON_VALUE_OPTIONS else 1
    return None


def _split_at_double_dash(arguments: List[str]) -> Tuple[List[str], Tuple[str, ...]]:
    if "--" not in arguments:
        return arguments, ()
    index = arguments.index("--")
    return arguments[:index], tuple(arguments[index + 1 :])


def _first_name(words: List[str]) -> Optional[str]:
    return next((word for word in words if not word.startswith("-")), None)


def _script_name(program: str, head: List[str]) -> Optional[str]:
    if program == "npm":
        if head[:1] in (["test"], ["t"]):
            return "test"
        if head[:1] in (["run"], ["run-script"]):
            return _first_name(head[1:])
        return None
    if program in ("yarn", "pnpm"):
        return _first_name(head[1:]) if head[:1] == ["run"] else _first_name(head)
    if program == "bun":
        return _first_name(head[1:]) if head[:1] == ["run"] else None
    return None


def _package_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    program = command[0]
    head, appended = _split_at_double_dash(command[1:])
    name = _script_name(program, head)
    found = _last_holding(place, "package.json")
    if name is None or found is None:
        return [_unrecognised(place, program)]
    index, path = found
    relative = _relative(place.root, path)
    manifest = _json_object(place.root, path)
    scripts = manifest.get("scripts") if manifest is not None else None
    text = scripts.get(name) if isinstance(scripts, dict) else None
    key = (path, name)
    if not isinstance(text, str) or key in place.scripts:
        return [_unrecognised(place, program, relative)]
    folders = place.folders[: index + 1] if place.folders is not None else None
    inner = place._replace(folders=folders, file=relative, scripts=place.scripts | {key})
    return _command_reaches(inner, text, appended)


def _last_holding(place: _Place, name: str) -> Optional[Tuple[int, str]]:
    folders = place.folders or ()
    held = [(index, os.path.join(folder, name)) for index, folder in enumerate(folders)]
    present = [entry for entry in held if os.path.lexists(entry[1])]
    return present[-1] if present else None


def _named_or_found(place: _Place, given: Optional[str], name: str) -> Optional[str]:
    found = _last_holding(place, name)
    return given if given is not None else found[1] if found is not None else None


def _relative(root: str, path: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def _inside(root: str, path: str) -> bool:
    return os.path.commonpath([root, path]) == root


def _read_inside(root: str, path: str) -> Optional[str]:
    real = os.path.realpath(path)
    if not _inside(root, real):
        return None
    try:
        with open(real, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _judged_file(
    place: _Place, word: str, path: str, judge: Callable[[str, str], _Judged]
) -> Union[_Judged, List[_Reach]]:
    relative = _relative(place.root, path)
    text = _read_inside(place.root, path)
    return [_unrecognised(place, word, relative)] if text is None else judge(text, relative)


def _json_object(root: str, path: str) -> Optional[Dict[str, Any]]:
    text = _read_inside(root, path)
    return None if text is None else _loaded_object(text)


def _loaded_object(text: str) -> Optional[Dict[str, Any]]:
    try:
        loaded = json.loads(text)
    except ValueError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _option_value(arguments: List[str], names: Tuple[str, ...]) -> Optional[str]:
    values = [
        value
        for index, argument in enumerate(arguments)
        for value in _values_at(arguments, index, argument, names)
    ]
    return values[-1] if values else None


def _values_at(arguments: List[str], index: int, argument: str, names: Tuple[str, ...]) -> List[str]:
    if argument in names:
        return [arguments[index + 1]] if index + 1 < len(arguments) else []
    assigned = [argument.split("=", 1)[1] for name in names if argument.startswith(name + "=")]
    return assigned or [argument[len(name) :] for name in names if _is_attached_to_short_option(argument, name)]


def _is_attached_to_short_option(argument: str, name: str) -> bool:
    return _SHORT_OPTION.fullmatch(name) is not None and argument.startswith(name) and len(argument) > len(name)


def _number(text: Optional[str]) -> Optional[float]:
    try:
        return float(text) if text is not None else None
    except ValueError:
        return None


def _positive(text: Optional[str]) -> bool:
    number = _number(text)
    return number is not None and 0 < number < math.inf


def _zero(text: Optional[str]) -> bool:
    return _number(text) == 0


def _node_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    program, arguments = command[0], command[1:]
    if "--test" in arguments:
        return [] if _positive(_option_value(arguments, ("--test-timeout",))) else [_reach(place, "node-test")]
    script = script_argument(arguments, INTERPRETERS["node"])
    if script is None:
        return [_unrecognised(place, program)]
    entry = _given_path(place, script)
    texts = _script_texts(place.root, entry)
    if texts is None or not _starts_node_test(texts):
        return [_unrecognised(place, program)]
    if _node_test_bounded(texts):
        return []
    return [_reach(place, "node-test", _relative(place.root, os.path.realpath(entry)))]


def _given_path(place: _Place, given: str) -> str:
    folders = place.folders or (place.root,)
    if os.path.isabs(given):
        return os.path.normpath(given)
    candidates = [os.path.normpath(os.path.join(folder, given)) for folder in reversed(folders)]
    return next((candidate for candidate in candidates if os.path.lexists(candidate)), candidates[0])


def _script_texts(root: str, entry: str) -> Optional[Tuple[str, ...]]:
    first = _read_inside(root, entry)
    if first is None:
        return None
    start = os.path.realpath(entry)
    seen = {start}
    pending = [(start, first)]
    read: List[Tuple[str, str]] = []
    while pending:
        path, text = pending[0]
        pending = pending[1:]
        read = [*read, (path, text)]
        for target in _import_targets(root, path, text):
            if target in seen:
                continue
            seen.add(target)
            imported = _read_inside(root, target)
            if imported is not None:
                pending = [*pending, (target, imported)]
    exports = _node_test_exports(root, read)
    return tuple(_with_re_exports_resolved_to_node_test(root, path, text, exports) for path, text in read)


class _NodeTestNames(NamedTuple):
    run: FrozenSet[str]
    module: FrozenSet[str]


_NO_NAMES = _NodeTestNames(frozenset(), frozenset())
_NODE_TEST_ITSELF = _NodeTestNames(frozenset(["run"]), frozenset())


def _node_test_exports(root: str, read: List[Tuple[str, str]]) -> Dict[str, _NodeTestNames]:
    statements = [(path, _RE_EXPORT_CLAUSE.findall(_without_comments(text))) for path, text in read]
    exports: Dict[str, _NodeTestNames] = {}
    grown = True
    while grown:
        found = {path: _exported_names(root, path, clauses, exports) for path, clauses in statements}
        grown = found != exports
        exports = found
    return exports


def _exported_names(root: str, path: str, clauses: List[Tuple[str, str, str]], exports: Dict[str, _NodeTestNames]) -> _NodeTestNames:
    run: FrozenSet[str] = frozenset()
    module: FrozenSet[str] = frozenset()
    for namespace, braces, specifier in clauses:
        source = _source_names(root, path, specifier, exports)
        if namespace and "run" in source.run:
            module = module | {namespace}
        elif braces is not None and braces.startswith("{"):
            pairs = [_renamed(entry) for entry in braces[1:-1].split(",") if entry.strip()]
            run = run | {exported for original, exported in pairs if original in source.run}
            module = module | {exported for original, exported in pairs if original in source.module}
        elif not namespace:
            run = run | source.run
            module = module | source.module
    return _NodeTestNames(run, module)


def _source_names(root: str, path: str, specifier: str, exports: Dict[str, _NodeTestNames]) -> _NodeTestNames:
    if specifier == "node:test":
        return _NODE_TEST_ITSELF
    if not specifier.startswith("."):
        return _NO_NAMES
    return exports.get(_resolved_import(root, os.path.dirname(path), specifier) or "", _NO_NAMES)


def _renamed(entry: str) -> Tuple[str, str]:
    words = entry.split()
    return (words[0], words[-1]) if len(words) == 3 and words[1] == "as" else (entry.strip(), entry.strip())


def _with_re_exports_resolved_to_node_test(root: str, path: str, text: str, exports: Dict[str, _NodeTestNames]) -> str:
    folder = os.path.dirname(path)

    def names_of(specifier: str) -> _NodeTestNames:
        return exports.get(_resolved_import(root, folder, specifier) or "", _NO_NAMES)

    def clause(statement: "re.Match[str]") -> str:
        braces, quote, specifier = statement.groups()
        names = names_of(specifier)
        if not (names.run or names.module):
            return statement.group(0)
        pairs = [_renamed(entry) for entry in braces.split(",") if entry.strip()]
        runs = ["run as " + local for original, local in pairs if original in names.run]
        modules = ["import * as {} from {}node:test{};".format(local, quote, quote) for original, local in pairs if original in names.module]
        imported = ["import {{ {} }} from {}node:test{};".format(", ".join(runs), quote, quote)] if runs else []
        return " ".join(imported + modules) or statement.group(0)

    def members_renamed(rewritten: str) -> str:
        for namespace, _, specifier in _NAMESPACE_IMPORT.findall(text):
            for renamed in names_of(specifier).run - {"run"}:
                member = r"(?<![\w$.])" + re.escape(namespace) + r"\s*\.\s*" + re.escape(renamed) + r"(?![\w$])"
                rewritten = re.sub(member, namespace + ".run", rewritten)
        return rewritten

    def source(found: "re.Match[str]") -> str:
        lead, quote, specifier = found.groups()
        return lead + quote + "node:test" + quote if names_of(specifier).run else found.group(0)

    return _RELATIVE_SOURCE.sub(source, members_renamed(_IMPORT_CLAUSE.sub(clause, text)))


def _import_targets(root: str, path: str, text: str) -> List[str]:
    folder = os.path.dirname(path)
    resolved = [_resolved_import(root, folder, specifier) for specifier in _RELATIVE_SPECIFIER.findall(text)]
    return [target for target in resolved if target is not None]


def _resolved_import(root: str, folder: str, specifier: str) -> Optional[str]:
    base = os.path.normpath(os.path.join(folder, specifier))
    tried = [base]
    if not posixpath.splitext(specifier)[1]:
        tried = [
            base,
            *[base + extension for extension in _IMPORT_EXTENSIONS],
            *[os.path.join(base, "index" + extension) for extension in _IMPORT_EXTENSIONS],
        ]
    found = next((candidate for candidate in tried if os.path.isfile(candidate)), None)
    if found is None:
        return None
    real = os.path.realpath(found)
    return real if _inside(root, real) else None


def _without_comments(text: str) -> str:
    return _SOURCE_TOKEN.sub(lambda token: token.group(1) or " ", text)


def _code_of(text: str) -> str:
    return _SOURCE_TOKEN.sub(_code_token, text)


def _code_token(token: "re.Match[str]") -> str:
    literal = token.group(1)
    if literal is None:
        return " "
    return literal if literal[1:-1] in _KEPT_LITERALS else _BLANK_LITERAL


def _names_bound_to_node_test(code: str) -> FrozenSet[str]:
    direct = {name for pattern in _NODE_TEST_BINDINGS for name in pattern.findall(code)}
    aliases = _ALIAS.findall(code)
    bound = set(direct)
    grown = True
    while grown:
        added = {name for name, source in aliases if source in bound} - bound
        bound = bound | added
        grown = bool(added)
    return frozenset(bound)


def _binds_node_test_run(text_code: str) -> bool:
    code = _RE_EXPORT_CLAUSE.sub(" ", text_code)
    if _RUN_FROM_NODE_TEST.search(code):
        return True
    names = _names_bound_to_node_test(code)
    return bool(names) and any(_uses_run_of(re.escape(name), code) for name in names)


def _uses_run_of(name: str, code: str) -> bool:
    member = r"(?<![\w$.])" + name + _RUN_MEMBER
    destructured = _RUN_IN_BRACES + r"\s*=\s*(?:await\s+)?" + name + r"(?![\w$])"
    return bool(re.search(member, code) or re.search(destructured, code))


def _starts_node_test(texts: Tuple[str, ...]) -> bool:
    flagged = any(_QUOTED_TEST_FLAG.search(_without_comments(text)) for text in texts)
    codes = tuple(_code_of(text) for text in texts)
    return flagged or any(_binds_node_test_run(code) for code in codes)


def _node_test_bounded(texts: Tuple[str, ...]) -> bool:
    flagged = any(_positive(value) for text in texts for value in _TEXT_TEST_TIMEOUT.findall(_without_comments(text)))
    codes = tuple(_code_of(text) for text in texts)
    calling = tuple(code for code in codes if _binds_node_test_run(code))
    return flagged or any(_bounding_run_timeout(value) for code in calling for value in _RUN_TIMEOUT.findall(code))


def _bounding_run_timeout(value: str) -> bool:
    if value in _NOT_A_BOUND:
        return False
    number = _number(value)
    return number is None or 0 < number < math.inf


def _given_config(place: _Place, arguments: List[str], names: Tuple[str, ...]) -> Optional[str]:
    given = _option_value(arguments, names)
    return _given_path(place, given) if given is not None else None


def _config_reaches(
    place: _Place,
    runner: str,
    prefixes: Tuple[str, ...],
    turned_off: Callable[[str], bool],
    given: Optional[str] = None,
) -> List[_Reach]:
    def judged(text: str, relative: str) -> List[_Reach]:
        return [_reach(place, runner, relative)] if turned_off(text) else []

    for path in _config_files(place, prefixes, given):
        found = _judged_file(place, runner, path, judged)
        if found:
            return found
    return []


def _config_files(place: _Place, prefixes: Tuple[str, ...], given: Optional[str]) -> List[str]:
    if given is not None:
        within = _inside(place.root, os.path.realpath(given))
        return _prefixed_files(given, prefixes) if within and os.path.isdir(given) else [given]
    for folder in reversed(place.folders or ()):
        matching = _prefixed_files(folder, prefixes)
        if matching:
            return matching
    return []


def _prefixed_files(folder: str, prefixes: Tuple[str, ...]) -> List[str]:
    try:
        names = sorted(os.listdir(folder))
    except (FileNotFoundError, NotADirectoryError):
        names = []
    return [os.path.join(folder, name) for name in names if name.startswith(prefixes)]


def _vitest_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    arguments = command[1:]
    if _zero(_option_value(arguments, ("--testTimeout", "--test-timeout"))):
        return [_reach(place, "vitest")]
    given = _given_config(place, arguments, _CONFIG_OPTIONS)
    return _config_reaches(place, "vitest", ("vitest.config.", "vite.config."), _ZERO_TEST_TIMEOUT.search, given)


def _jest_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    arguments = command[1:]
    if _zero(_option_value(arguments, ("--testTimeout",))):
        return [_reach(place, "jest")]
    given = _option_value(arguments, _CONFIG_OPTIONS)
    if given is None:
        configured = _config_reaches(place, "jest", ("jest.config.",), _ZERO_TEST_TIMEOUT.search)
        return configured or _package_setting_reaches(place, "jest", _jest_section_turns_off)
    if given.lstrip().startswith("{"):
        return _inline_jest_reaches(place, given)
    if posixpath.basename(given) == "package.json":
        return _package_setting_reaches(place, "jest", _jest_section_turns_off, _given_path(place, given))
    return _config_reaches(place, "jest", ("jest.config.",), _ZERO_TEST_TIMEOUT.search, _given_path(place, given))


def _jest_section_turns_off(section: Dict[str, Any]) -> bool:
    return section.get("testTimeout") == 0


def _inline_jest_reaches(place: _Place, given: str) -> List[_Reach]:
    try:
        section = json.loads(given)
    except ValueError:
        return [_unrecognised(place, "jest")]
    if not isinstance(section, dict):
        return [_unrecognised(place, "jest")]
    return [_reach(place, "jest")] if _jest_section_turns_off(section) else []


def _package_setting_reaches(
    place: _Place, runner: str, turned_off: Callable[[Dict[str, Any]], bool], given: Optional[str] = None
) -> List[_Reach]:
    path = _named_or_found(place, given, "package.json")
    if path is None:
        return []
    def judged(text: str, relative: str) -> List[_Reach]:
        section = (_loaded_object(text) or {}).get(runner)
        return [_reach(place, runner, relative)] if isinstance(section, dict) and turned_off(section) else []

    return _judged_file(place, runner, path, judged)


def _mocha_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    arguments = command[1:]
    value = _option_value(arguments, ("--timeout", "-t"))
    if "--no-timeouts" in arguments or _zero(value) or value == "false":
        return [_reach(place, "mocha")]
    given = _given_config(place, arguments, ("--config",))
    configured = _config_reaches(place, "mocha", (".mocharc.",), _MOCHA_TIMEOUT_OFF.search, given)
    if configured:
        return configured
    package = _given_config(place, arguments, ("--package",))
    return _package_setting_reaches(place, "mocha", _mocha_section_turns_off, package)


def _mocha_section_turns_off(section: Dict[str, Any]) -> bool:
    timeout = section.get("timeout")
    return timeout is False or timeout == "0" or (not isinstance(timeout, bool) and timeout == 0)


def _playwright_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    if command[1:2] != ["test"]:
        return [_unrecognised(place, command[0])]
    arguments = command[2:]
    if _zero(_option_value(arguments, ("--timeout",))):
        return [_reach(place, "playwright")]
    given = _given_config(place, arguments, _CONFIG_OPTIONS)
    return _config_reaches(place, "playwright", ("playwright.config.",), _ZERO_TIMEOUT.search, given)


def _go_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    if command[1:2] != ["test"]:
        return [_unrecognised(place, command[0])]
    value = _option_value(command[2:], ("-timeout", "--timeout"))
    return [_reach(place, "go-test")] if value is not None and _GO_ZERO_DURATION.fullmatch(value) else []


def _dart_family_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    program = command[0]
    if command[1:2] != ["test"]:
        return [_unrecognised(place, program)]
    runner = "{}-test".format(program)
    value = _option_value(command[2:], ("--timeout",))
    if value is not None and value.lower() == "none":
        return [_reach(place, runner)]
    found = _last_holding(place, "dart_test.yaml")
    if found is None:
        return []
    def judged(text: str, relative: str) -> List[_Reach]:
        return [_reach(place, runner, relative)] if _DART_TIMEOUT_OFF.search(text) else []

    return _judged_file(place, program, found[1], judged)


def _pytest_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    arguments = command[1:]
    timeout = _option_value(arguments, ("--timeout",))
    if timeout is not None:
        return [] if _positive(timeout) else [_reach(place, "pytest")]
    given = _given_config(place, arguments, ("-c", "--config-file"))
    if given is not None:
        section = _PYTEST_SECTION_BY_EXTENSION.get(posixpath.splitext(given)[1], "pytest")
        return _pytest_file_reaches(place, given, section, True) or []
    for folder in reversed(place.folders or ()):
        for name, section in _PYTEST_CONFIGS:
            path = os.path.join(folder, name)
            if not os.path.lexists(path):
                continue
            decided = _pytest_file_reaches(place, path, section, name == "pytest.ini")
            if decided is not None:
                return decided
    return [_reach(place, "pytest")]


def _pytest_file_reaches(place: _Place, path: str, section: str, decides: bool) -> Optional[List[_Reach]]:
    return _judged_file(
        place, "pytest", path, lambda text, relative: _pytest_text_reaches(place, text, relative, section, decides)
    )


def _pytest_text_reaches(place: _Place, text: str, relative: str, section: str, decides: bool) -> Optional[List[_Reach]]:
    try:
        holds, value = _pytest_setting(section, text)
    except configparser.Error:
        return [_unrecognised(place, "pytest", relative)]
    if not (holds or decides):
        return None
    if _positive(value):
        return []
    return [_reach(place, "pytest", relative if value is not None else None)]


def _pytest_setting(section: str, text: str) -> Tuple[bool, Optional[str]]:
    if section == _PYPROJECT_SECTION:
        return _pyproject_timeout(text)
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read_string(text)
    if not parser.has_section(section):
        return False, None
    value = parser.get(section, "timeout", fallback=None)
    return True, value.strip() if value is not None else None


def _pyproject_timeout(text: str) -> Tuple[bool, Optional[str]]:
    holds = False
    within = False
    value: Optional[str] = None
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("["):
            within = stripped == "[{}]".format(_PYPROJECT_SECTION)
            holds = holds or within
        elif within and "=" in stripped:
            key, raw = stripped.split("=", 1)
            if key.strip() == "timeout":
                value = raw.strip().strip("'\"")
    return holds, value


def _unittest_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    return [_reach(place, "unittest")]


def _cargo_reaches(place: _Place, command: List[str]) -> List[_Reach]:
    if command[1:2] == ["test"]:
        return [_reach(place, "cargo-test")]
    if command[1:3] != ["nextest", "run"]:
        return [_unrecognised(place, command[0])]
    given = _given_config(place, command[3:], ("--config-file",))
    path = _named_or_found(place, given, _NEXTEST_CONFIG)
    if path is None:
        return [_reach(place, "cargo-nextest")]
    def judged(text: str, relative: str) -> List[_Reach]:
        return [] if _nextest_profile_bounded(text, _nextest_profile(place, command[3:])) else [_reach(place, "cargo-nextest")]

    return _judged_file(place, command[0], path, judged)


def _nextest_profile(place: _Place, arguments: List[str]) -> str:
    named = _option_value(arguments, ("--profile", "-P"))
    assigned = [word[len(_NEXTEST_PROFILE_VARIABLE) :] for word in place.assignments if word.startswith(_NEXTEST_PROFILE_VARIABLE)]
    return named or (assigned[-1] if assigned else _NEXTEST_DEFAULT_PROFILE)


def _nextest_profile_bounded(text: str, profile: str) -> bool:
    timeouts = _nextest_timeouts(text)
    return timeouts.get(profile, timeouts.get(_NEXTEST_DEFAULT_PROFILE, False))


def _nextest_timeouts(text: str) -> Dict[str, bool]:
    timeouts: Dict[str, bool] = {}
    section: Optional[str] = ""
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("[["):
            section = None
        elif stripped.startswith("["):
            section = stripped.strip("[] ")
        elif section is not None and "=" in stripped:
            key, value = stripped.split("=", 1)
            timeouts = _with_nextest_setting(timeouts, _dotted(section, key), value)
    return timeouts


def _dotted(section: str, key: str) -> str:
    return ".".join(part for part in (section, key.strip()) if part).replace('"', "").replace("'", "")


def _with_nextest_setting(timeouts: Dict[str, bool], path: str, value: str) -> Dict[str, bool]:
    found = _NEXTEST_TIMEOUT_KEY.fullmatch(path)
    if found is None:
        return timeouts
    profile, member = found.groups()
    if member is None:
        inline = _TERMINATE_AFTER.search(value)
        return {**timeouts, profile: inline is not None and _positive(inline.group(1))}
    terminates = member == _NEXTEST_TERMINATE_KEY and _positive(value.strip())
    return {**timeouts, profile: timeouts.get(profile, False) or terminates}


_RUNNERS: Dict[str, _Runner] = {
    "node": _node_reaches,
    "tsx": _node_reaches,
    "npm": _package_reaches,
    "yarn": _package_reaches,
    "pnpm": _package_reaches,
    "bun": _package_reaches,
    "vitest": _vitest_reaches,
    "jest": _jest_reaches,
    "mocha": _mocha_reaches,
    "playwright": _playwright_reaches,
    "go": _go_reaches,
    "dart": _dart_family_reaches,
    "flutter": _dart_family_reaches,
    "pytest": _pytest_reaches,
    "unittest": _unittest_reaches,
    "cargo": _cargo_reaches,
}
