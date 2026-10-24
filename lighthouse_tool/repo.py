import argparse
import json
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool.records import write_atomically

GIT_ENVIRONMENT_OVERRIDES = {"GIT_TERMINAL_PROMPT": "0"}
ANSWERS_FILE = "answers.json"


class Refusal(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Refusal(message)


def git(repo: str, args: List[str]) -> Tuple[int, str, str]:
    completed = subprocess.run(
        ["git", "-C", repo, *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENVIRONMENT_OVERRIDES},
    )
    return completed.returncode, completed.stdout, completed.stderr


def checked_git(where: str, args: List[str]) -> str:
    code, stdout, stderr = git(where, args)
    if code != 0:
        raise Refusal("git {} failed: {}".format(args[0], stderr.strip()))
    return stdout


def toplevel(repo: str) -> Optional[str]:
    code, stdout, _ = git(repo, ["rev-parse", "--show-toplevel"])
    path = stdout.strip()
    return os.path.realpath(path) if code == 0 and path else None


def require_root(repo: str) -> str:
    root = toplevel(repo)
    if root is None:
        raise Refusal("{} is not a git repository".format(repo))
    return root


def repository_folder(repo: str) -> Optional[str]:
    code, stdout, _ = git(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
    common_dir = os.path.normpath(stdout.strip()) if code == 0 and stdout.strip() else ""
    if common_dir.endswith(".git"):
        return os.path.basename(os.path.dirname(common_dir))
    top = toplevel(repo)
    return os.path.basename(top) if top else None


def state_dir(repo: str) -> Optional[str]:
    folder = repository_folder(repo)
    return os.path.join(os.path.expanduser("~"), ".lighthouse", folder) if folder else None


def ensure_state_dir(repo: str) -> Optional[str]:
    path = state_dir(repo)
    if path is None:
        return None
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def read_answers(repo: str) -> Dict[str, Any]:
    folder = state_dir(repo)
    if folder is None:
        return {}
    try:
        with open(os.path.join(folder, ANSWERS_FILE), encoding="utf-8") as answers_file:
            answers = json.load(answers_file)
    except (OSError, ValueError):
        return {}
    return dict(answers) if isinstance(answers, dict) else {}


def write_answers(folder: str, answers: Dict[str, Any]) -> None:
    write_atomically(os.path.join(folder, ANSWERS_FILE), json.dumps(answers, indent=2) + "\n")


def commit_of(repo: str, ref: str) -> Optional[str]:
    code, stdout, _ = git(repo, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"])
    commit = stdout.strip()
    return commit if code == 0 and commit else None


def is_branch_name(repo: str, name: str) -> bool:
    if not name or name.startswith("-"):
        return False
    code, _, _ = git(repo, ["check-ref-format", "refs/heads/" + name])
    return code == 0


def has_origin(repo: str) -> bool:
    code, stdout, _ = git(repo, ["remote"])
    return code == 0 and "origin" in stdout.split()


def origin_holds(repo: str, name: str) -> bool:
    code, stdout, _ = git(repo, ["ls-remote", "--heads", "origin", name])
    wanted = "refs/heads/" + name
    return code == 0 and any(line.split("\t")[-1] == wanted for line in stdout.splitlines())


def resolve_branch(repo: str, name: str) -> Optional[str]:
    if not is_branch_name(repo, name):
        return None
    if has_origin(repo):
        git(repo, ["fetch", "--quiet", "origin"])
        remote_commit = commit_of(repo, "refs/remotes/origin/" + name) if origin_holds(repo, name) else None
        if remote_commit:
            return remote_commit
    return commit_of(repo, "refs/heads/" + name)


def load_profile(repo: str, path: Optional[str] = None) -> Optional[Any]:
    profile_path = path or os.path.join(toplevel(repo) or repo, ".lighthouse", "profile.json")
    try:
        with open(profile_path, encoding="utf-8") as profile_file:
            return json.load(profile_file)
    except (OSError, ValueError):
        return None
