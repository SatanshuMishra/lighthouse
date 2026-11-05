import importlib.util
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
import unittest
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tests import scratch

ROOT = scratch.ROOT
LIGHTHOUSE = scratch.LIGHTHOUSE
REFEREE = os.path.join(ROOT, "tests", "contracts")
COMMAND_SECONDS = 300
POLL_SECONDS = 0.1
TYPED = "typed\n"
FEATURE = "feature"
CORE = "main"
NONINTERACTIVE_NAMES = (
    "GIT_TERMINAL_PROMPT",
    "GCM_INTERACTIVE",
    "GH_PROMPT_DISABLED",
    "GIT_PAGER",
    "PAGER",
    "GIT_SSH_COMMAND",
)
GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
GIT_CONFIG_NAMES = ("GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS")
RECORDED_CONFIG = ("http.lowSpeedLimit", "http.lowSpeedTime")
SSH_OPTIONS = ("-o BatchMode=yes", "-o ServerAliveInterval=15", "-o ServerAliveCountMax=4")
H11 = "h11-interphase-record"
H13 = "h13-lighthouse-verdict-line"
H14 = "h14-lighthouse-findings"
H15 = "h15-pr-fields"
H16 = "h16-pr-render"
K1 = "k1-acceptance"
CLI_SURFACE = {"family": "cli", "target": "bin/lighthouse"}
DIRECT_CHECK = {"kind": "direct", "why": "it answers"}
PASSED_SUITE = {
    "result": "passed",
    "reason": None,
    "failures": [],
    "pre_existing": [],
    "flaky": [],
    "core": None,
    "feature": None,
}
GREEN_LINE = {
    "verdict": "green",
    "failures": [],
    "unproven": [],
    "flaky": [],
    "tokens": 1200,
    "minutes": 3,
    "dollars": 1.25,
    "pr": None,
}
CORE_COMMIT = "1" * 40
FEATURE_COMMIT = "2" * 40


def referee_validator() -> Any:
    spec = importlib.util.spec_from_file_location("referee_validator", os.path.join(REFEREE, "validator.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def referee_errors(name: str, value: Any) -> Tuple[str, ...]:
    return tuple(referee_validator().errors_against(REFEREE, name, value))


def referee_form_errors(name: str, form: str, value: Any) -> Tuple[str, ...]:
    reference = {"$ref": "{}.schema.json#/$defs/{}".format(name, form)}
    return tuple(referee_validator().errors(reference, value, REFEREE))


def blocked_line(reason: str) -> Dict[str, Any]:
    return {
        "verdict": "blocked",
        "failures": [],
        "unproven": [],
        "flaky": [],
        "tokens": 0,
        "minutes": 0,
        "pr": None,
        "reason": reason,
    }


def exact_line(identifier: str, command: str, target: str = "bin/lighthouse") -> Dict[str, Any]:
    return {
        "id": identifier,
        "kind": "exact",
        "surface": {"family": "cli", "target": target},
        "command": command,
        "pass": "exit 0",
    }


def record_with(lines: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    tests = [
        {
            "file": "tests/test_accept_record.py",
            "name": "Record.test_line_{}".format(index),
            "given": "the acceptance line {}".format(line.get("id", index) if isinstance(line, dict) else index),
            "expect": "it passes",
            "step": "build",
            **({"check": line["id"]} if isinstance(line, dict) and isinstance(line.get("id"), str) else {}),
        }
        for index, line in enumerate(lines)
    ]
    return {
        "seams": [
            {
                "name": "lighthouse-cli",
                "interface": "bin/lighthouse subcommands run as processes",
                "catches": "behaviour the commands show",
                "misses": "what a real model replies",
                "builder_runs": True,
            }
        ],
        "criteria": [
            {
                "number": "5.1",
                "title": "The acceptance lines run",
                "text": "WHEN lighthouse execute runs, THE SYSTEM SHALL run each acceptance line.",
                "seam": "lighthouse-cli",
                "tests": tests,
                "acceptance": [dict(line) for line in lines],
            }
        ],
        "steps": [{"name": "build", "files": ["lighthouse_tool/execute.py"], "criteria": ["5.1"]}],
        "status": "handed-off",
    }


def valid_findings(**overrides: Any) -> Dict[str, Any]:
    findings = {
        "version": 1,
        "suite": dict(PASSED_SUITE),
        "build": {"result": "ok", "reason": None},
        "paths": [
            {
                "name": "one",
                "kind": "new",
                "surface": "cli",
                "expected": "works",
                "evidence": ["evidence/one.log"],
                "status": "passed",
                "retry": None,
                "core": None,
                "trials": None,
                "check": dict(DIRECT_CHECK),
            }
        ],
        "spend": {"tokens": 10, "minutes": 1, "dollars": None},
    }
    return {**findings, **overrides}


def with_path(findings: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
    first = {**findings["paths"][0], **changes}
    return {**findings, "paths": [first, *findings["paths"][1:]]}


def write_json(path: str, value: Any) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2) + "\n")
    return path


def write_text(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def json_lines(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle.read().splitlines() if line.strip()]


def last_json(stdout: str) -> Any:
    lines = stdout.strip().splitlines()
    if not lines:
        raise AssertionError("the command printed nothing on stdout")
    return json.loads(lines[-1])


def folder(test: unittest.TestCase, prefix: str) -> str:
    return scratch.temporary_folder(test, prefix)


def results_folder(test: unittest.TestCase) -> str:
    return os.path.join(folder(test, "lh-results-"), "results")


def real_git() -> str:
    found = shutil.which("git")
    if found is None:
        raise AssertionError("git is not on PATH")
    return os.path.realpath(found)


def stripped_environment() -> Dict[str, str]:
    return {
        name: value
        for name, value in scratch.base_environment().items()
        if name not in NONINTERACTIVE_NAMES
        and name not in GIT_CONFIG_NAMES
        and not name.startswith(GIT_CONFIG_PREFIXES)
    }


def environment(
    test: unittest.TestCase,
    stubs: Optional[str] = None,
    extra: Optional[Dict[str, str]] = None,
    without: Sequence[str] = (),
    home: Optional[str] = None,
) -> Dict[str, str]:
    base = stripped_environment()
    path = base.get("PATH", os.defpath)
    for program in without:
        path = os.pathsep.join(
            entry for entry in path.split(os.pathsep) if entry and not os.access(os.path.join(entry, program), os.X_OK)
        )
    return {
        **base,
        "HOME": home if home is not None else scratch.make_home(test),
        "PLUGIN_METRICS_DIR": folder(test, "lh-store-"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "PATH": os.pathsep.join([stubs, path]) if stubs else path,
        **(extra or {}),
    }


def lighthouse(
    args: Sequence[str], env: Dict[str, str], stdin_text: Optional[str] = None, cwd: Optional[str] = None
) -> Tuple[int, str, str]:
    feeding = {"input": stdin_text} if stdin_text is not None else {"stdin": subprocess.DEVNULL}
    completed = subprocess.run(
        [sys.executable, LIGHTHOUSE, *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=COMMAND_SECONDS,
        **feeding,
    )
    return completed.returncode, completed.stdout, completed.stderr


def feature_repo(
    test: unittest.TestCase, feature_files: Optional[Dict[str, str]] = None, stay_on_feature: bool = False
) -> Tuple[str, str]:
    repo, _ = scratch.make_repo(test)
    scratch.run_git(repo, "checkout", "-q", "-b", FEATURE)
    commit = scratch.commit_files(repo, feature_files or {"feature.txt": "only on the feature branch\n"}, "add the feature")
    if not stay_on_feature:
        scratch.run_git(repo, "checkout", "-q", CORE)
    return repo, commit


def worktrees(test: unittest.TestCase, repo: str, results: str, env: Dict[str, str], stdin_text: Optional[str] = None) -> None:
    code, stdout, stderr = lighthouse(
        ["worktrees", "--repo", repo, "--core", CORE, "--feature", FEATURE, "--results", results], env, stdin_text
    )
    test.assertEqual(code, 0, stdout + stderr)


def wait_for(condition: Any, seconds: float, what: str) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() >= deadline:
            raise AssertionError("gave up after {:g} seconds waiting for {}".format(seconds, what))
        time.sleep(POLL_SECONDS)


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_quietly(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def stop_process(process: "subprocess.Popen[Any]") -> None:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=30)


def stop_processes_naming(text: str) -> None:
    listing = subprocess.run(
        ["ps", "-A", "-o", "pid=,command="],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    named = [
        int(parts[0])
        for parts in (line.strip().split(None, 1) for line in listing.stdout.splitlines())
        if len(parts) == 2 and parts[0].isdigit() and text in parts[1] and int(parts[0]) != os.getpid()
    ]
    for pid in sorted(named):
        stop_quietly(pid)


def replace_text(path: str, text: str) -> None:
    partial = path + ".part"
    with open(partial, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(partial, path)


OBSERVE = """
import json
import os
import subprocess
import sys

REAL_GIT = {git!r}
NAMES = {names!r}
CONFIG = {config!r}


def given_input():
    return sys.stdin.read() if sys.stdin is not None else ""


def configured(key):
    done = subprocess.run(
        [REAL_GIT, "config", "--get", key],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return done.stdout.strip()


def observed(stdin_text, keys=()):
    return {{
        "argv": sys.argv[1:],
        "cwd": os.getcwd(),
        "stdin": stdin_text,
        "env": {{name: os.environ.get(name) for name in NAMES}},
        "config": {{key: configured(key) for key in (*CONFIG, *keys)}},
    }}
"""

RECORDER = """#!{python}
{observe}

target = sys.argv[1]
record = observed(given_input(), tuple(sys.argv[2:]))
with open(target + ".part", "w", encoding="utf-8") as handle:
    handle.write(json.dumps(record))
os.replace(target + ".part", target)
sys.exit(0)
"""

GIT_WRAPPER = """#!{python}
{observe}

CALLS = {calls!r}
record = observed(given_input())
with open(CALLS, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\\n")
os.execv(REAL_GIT, [REAL_GIT, *sys.argv[1:]])
"""

GH_STUB = """#!{python}
{observe}

CALLS = {calls!r}
record = observed(given_input())
with open(CALLS, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\\n")
print("[]")
sys.exit(0)
"""

CLAUDE_STUB = """#!{python}
{observe}

CALLS = {calls!r}
REPLIES = {replies!r}
RESULTS = {results!r}
record = observed(given_input())
with open(CALLS, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\\n")
with open(CALLS, encoding="utf-8") as handle:
    index = len([line for line in handle.read().splitlines() if line.strip()]) - 1
with open(REPLIES, encoding="utf-8") as handle:
    replies = json.load(handle)
if index >= len(replies):
    sys.stdout.write("no scripted reply for call {{}}".format(index + 1))
    sys.exit(3)
reply = replies[index]
for name, text in sorted(reply.get("files", {{}}).items()):
    path = os.path.join(RESULTS, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
if "envelope" in reply:
    sys.stdout.write(json.dumps(reply["envelope"]))
    sys.exit(0)
sys.stdout.write(reply["raw"])
sys.exit(reply.get("exit", 0))
"""

PULL_REQUEST_STUB = """#!{python}
{observe}

CALLS = {calls!r}
REPLY = {reply!r}
record = observed(given_input())
arguments = sys.argv[1:]
fields = None
if "--fields" in arguments[:-1]:
    with open(arguments[arguments.index("--fields") + 1], encoding="utf-8") as handle:
        fields = handle.read()
record["fields"] = fields
with open(CALLS, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\\n")
sys.stdout.write(REPLY + "\\n")
sys.exit(0)
"""

CAFFEINATE_STUB = """#!{python}
import sys

sys.exit(0)
"""

SYSTEMD_INHIBIT_STUB = """#!{python}
import os
import sys

wrapped = [argument for argument in sys.argv[1:] if not argument.startswith("--what=") and not argument.startswith("--why=")]
os.execvp(wrapped[0], wrapped)
"""


def observe_code(git: str) -> str:
    return OBSERVE.format(git=git, names=NONINTERACTIVE_NAMES, config=RECORDED_CONFIG)


def write_program(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o755)
    return path


class Stubs:
    def __init__(self, test: unittest.TestCase, git: Optional[str] = None) -> None:
        self.git = git or real_git()
        self.folder = folder(test, "lh-stubs-")
        self.calls_folder = folder(test, "lh-calls-")
        self.observe = observe_code(self.git)
        write_program(os.path.join(self.folder, "caffeinate"), CAFFEINATE_STUB.format(python=sys.executable))
        write_program(os.path.join(self.folder, "systemd-inhibit"), SYSTEMD_INHIBIT_STUB.format(python=sys.executable))
        self.gh()

    def calls_path(self, name: str) -> str:
        return os.path.join(self.calls_folder, name + "-calls.jsonl")

    def calls(self, name: str) -> List[Dict[str, Any]]:
        return json_lines(self.calls_path(name))

    def gh(self) -> None:
        write_program(
            os.path.join(self.folder, "gh"),
            GH_STUB.format(python=sys.executable, observe=self.observe, calls=self.calls_path("gh")),
        )

    def git_wrapper(self) -> None:
        write_program(
            os.path.join(self.folder, "git"),
            GIT_WRAPPER.format(python=sys.executable, observe=self.observe, calls=self.calls_path("git")),
        )

    def claude(self, results: str, replies: Sequence[Dict[str, Any]]) -> None:
        replies_path = write_json(os.path.join(self.calls_folder, "claude-replies.json"), list(replies))
        write_program(
            os.path.join(self.folder, "claude"),
            CLAUDE_STUB.format(
                python=sys.executable,
                observe=self.observe,
                calls=self.calls_path("claude"),
                replies=replies_path,
                results=results,
            ),
        )

    def pull_request(self, reply: Dict[str, Any]) -> None:
        write_program(
            os.path.join(self.folder, "pull-request"),
            PULL_REQUEST_STUB.format(
                python=sys.executable,
                observe=self.observe,
                calls=self.calls_path("pull-request"),
                reply=json.dumps(reply),
            ),
        )


class Recorder:
    def __init__(self, test: unittest.TestCase, git: Optional[str] = None) -> None:
        tools = folder(test, "lh-tools-")
        self.records = folder(test, "lh-records-")
        self.path = write_program(
            os.path.join(tools, "recorder.py"),
            RECORDER.format(python=sys.executable, observe=observe_code(git or real_git())),
        )

    def record_path(self, name: str) -> str:
        return os.path.join(self.records, name + ".json")

    def argv(self, name: str, *keys: str) -> List[str]:
        return [sys.executable, self.path, self.record_path(name), *keys]

    def command(self, name: str, *keys: str) -> str:
        return " ".join(shlex.quote(part) for part in self.argv(name, *keys))

    def read(self, name: str) -> Dict[str, Any]:
        return read_json(self.record_path(name))


def assert_noninteractive(test: unittest.TestCase, record: Dict[str, Any], where: str) -> None:
    shown = "{}: {}".format(where, json.dumps({key: record.get(key) for key in ("argv", "stdin", "env", "config")}))
    test.assertEqual(record["stdin"], "", shown)
    env = record["env"]
    test.assertEqual(env["GIT_TERMINAL_PROMPT"], "0", shown)
    test.assertEqual(env["GCM_INTERACTIVE"], "never", shown)
    test.assertEqual(env["GH_PROMPT_DISABLED"], "1", shown)
    test.assertEqual(env["GIT_PAGER"], "cat", shown)
    test.assertEqual(env["PAGER"], "cat", shown)
    ssh = env["GIT_SSH_COMMAND"] or ""
    for option in SSH_OPTIONS:
        test.assertIn(option, ssh, shown)
    test.assertEqual(record["config"]["http.lowSpeedLimit"], "1", shown)
    test.assertEqual(record["config"]["http.lowSpeedTime"], "60", shown)


def commits_file(results: str, core: str = CORE_COMMIT, feature: str = FEATURE_COMMIT) -> str:
    return write_json(os.path.join(results, "commits.json"), {"core": core, "feature": feature})


def judged_results(test: unittest.TestCase, findings: Dict[str, Any], suite: Optional[Dict[str, Any]] = None) -> str:
    results = folder(test, "lh-results-")
    commits_file(results)
    write_json(os.path.join(results, "suite.json"), suite if suite is not None else dict(PASSED_SUITE))
    write_text(os.path.join(results, "evidence", "one.log"), "one\n")
    write_json(os.path.join(results, "findings.json"), findings)
    return results


def launch_flags(repo: str, results: str) -> List[str]:
    return ["--repo", repo, "--core", CORE, "--feature", FEATURE, "--results", results]


def launched(test: unittest.TestCase, replies: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    repo, _ = feature_repo(test)
    results = results_folder(test)
    stubs = Stubs(test)
    stubs.claude(results, replies)
    env = environment(test, stubs.folder)
    code, stdout, stderr = lighthouse(["launch", *launch_flags(repo, results)], env)
    return {"code": code, "stdout": stdout, "stderr": stderr, "results": results, "calls": stubs.calls("claude")}


def envelope(line: Any, session: str = "s1", result: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    body = {"session_id": session, "structured_output": {"verdict_line": line}, **extra}
    return {**body, "result": result} if result is not None else body


def prompt_of(argv: Sequence[str]) -> str:
    return argv[argv.index("-p") + 1] if "-p" in argv[:-1] else ""


def value_after(argv: Sequence[str], flag: str) -> Optional[str]:
    return argv[argv.index(flag) + 1] if flag in argv[:-1] else None


def no_line_in(path: str) -> bool:
    if not os.path.exists(path):
        return True
    with open(path, encoding="utf-8") as handle:
        return not [line for line in handle.read().splitlines() if line.strip()]


def plain_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text: str) -> str:
    return " ".join(text.split())


def section(text: str, heading: str) -> str:
    lines = text.splitlines()
    marker = "## " + heading
    starts = [index for index, line in enumerate(lines) if line.strip() == marker]
    if not starts:
        raise AssertionError("no {} heading".format(marker))
    following = [index for index in range(starts[0] + 1, len(lines)) if lines[index].startswith("## ")]
    end = following[0] if following else len(lines)
    return "\n".join(lines[starts[0] : end])
