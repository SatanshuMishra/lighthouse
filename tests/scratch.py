import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIGHTHOUSE = os.path.join(ROOT, "bin", "lighthouse")
WITHHELD_VARIABLES = ("CLAUDE_CODE_SESSION_ID", "SHIP")


def base_environment() -> Dict[str, str]:
    return {name: value for name, value in os.environ.items() if name not in WITHHELD_VARIABLES}


def git_environment() -> Dict[str, str]:
    return {
        **base_environment(),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


def run_git(repo: str, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", repo, *args],
        env=git_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("git {} failed: {}".format(" ".join(args), completed.stderr))
    return completed.stdout


def temporary_folder(test: unittest.TestCase, prefix: str) -> str:
    folder = os.path.realpath(tempfile.mkdtemp(prefix=prefix))
    test.addCleanup(shutil.rmtree, folder, True)
    return folder


def make_home(test: unittest.TestCase) -> str:
    return temporary_folder(test, "lh-home-")


def make_repo(test: unittest.TestCase) -> Tuple[str, str]:
    root = temporary_folder(test, "lh-repo-")
    remote = os.path.join(root, "remote.git")
    work = os.path.join(root, "work")
    run_git(root, "init", "-q", "--bare", "--initial-branch=main", remote)
    run_git(root, "clone", "-q", remote, work)
    run_git(work, "config", "user.name", "Lighthouse Test")
    run_git(work, "config", "user.email", "lighthouse@example.invalid")
    run_git(work, "config", "commit.gpgsign", "false")
    run_git(work, "symbolic-ref", "HEAD", "refs/heads/main")
    commit_files(work, {"README.md": "# scratch\n"}, "add the readme")
    run_git(work, "push", "-q", "-u", "origin", "main")
    return work, remote


def commit_files(repo: str, files: Dict[str, str], message: str) -> str:
    for relative_path, text in files.items():
        path = os.path.join(repo, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    run_git(repo, "add", "--", *files)
    run_git(repo, "commit", "-q", "-m", message)
    return run_git(repo, "rev-parse", "HEAD").strip()


GH_STUB = """#!{python}
import json
import os
import sys

ANSWERS = json.loads({answers!r})
CALLS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "gh-calls.jsonl")

arguments = sys.argv[1:]
with open(CALLS, "a", encoding="utf-8") as calls:
    calls.write(json.dumps(arguments) + "\\n")
if arguments[:2] == ["pr", "list"] and "--base" in arguments[:-1]:
    branch = arguments[arguments.index("--base") + 1]
    print(json.dumps(ANSWERS.get(branch, [])))
sys.exit(0)
"""


def stub_gh(folder: str, answers: Dict[str, List[Dict[str, Any]]]) -> str:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "gh")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(GH_STUB.format(python=sys.executable, answers=json.dumps(answers)))
    os.chmod(path, 0o755)
    return path


def environment(home: str, stub_folder: Optional[str] = None) -> Dict[str, str]:
    base = base_environment()
    path = base.get("PATH", os.defpath)
    return {
        **base,
        "HOME": home,
        "PATH": os.pathsep.join([stub_folder, path]) if stub_folder else path,
    }


def run_lighthouse(args: List[str], env: Dict[str, str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, LIGHTHOUSE, *args],
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def sample_profile(**overrides: Any) -> Dict[str, Any]:
    profile = {
        "version": 1,
        "sources": [],
        "suite": {"command": "python3 -m unittest discover", "junit": None, "timeout_minutes": None},
        "surfaces": [
            {
                "name": "cli",
                "kind": "command line",
                "paths": ["README.md"],
                "driver": "the shell",
                "available": True,
                "sign_in": {"method": "none", "command": None},
                "credentials": [],
                "trials": 1,
            }
        ],
        "credentials": {"file": None, "names": {}},
        "facts": {},
        "off_limits": [],
    }
    return {**profile, **overrides}


def write_profile(repo: str, profile: Dict[str, Any]) -> str:
    folder = os.path.join(repo, ".lighthouse")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "profile.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(profile, indent=2) + "\n")
    return path
