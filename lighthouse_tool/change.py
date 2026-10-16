import json
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool import repo as repository
from lighthouse_tool.repo import Parser, Refusal, checked_git, require_root

RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"
PULL_REQUEST_FIELDS = ("number", "title", "body", "url")


class MissingBranch(Refusal):
    def __init__(self, branch: str) -> None:
        super().__init__("branch {} does not exist locally or on origin".format(branch))
        self.branch = branch


def parser() -> Parser:
    arguments = Parser(prog="lighthouse change", add_help=False)
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--core", required=True)
    arguments.add_argument("--feature", required=True)
    return arguments


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        result = change_set(options.repo, options.core, options.feature)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse change: {}".format(refusal)
    return 0, json.dumps(result), None


def change_set(repo: str, core: str, feature: str) -> Dict[str, Any]:
    root = require_root(repo)
    core_commit = repository.resolve_branch(root, core)
    if core_commit is None:
        raise MissingBranch(core)
    feature_commit = repository.resolve_branch(root, feature)
    if feature_commit is None:
        raise MissingBranch(feature)
    pull_requests, pull_requests_error = merged_pull_requests(root, feature)
    return {
        "core": core,
        "feature": feature,
        "core_commit": core_commit,
        "feature_commit": feature_commit,
        "commits": commits_between(root, core_commit, feature_commit),
        "files": changed_files(root, core_commit, feature_commit),
        "pull_requests": pull_requests,
        "pull_requests_error": pull_requests_error,
    }


def commits_between(root: str, core_commit: str, feature_commit: str) -> List[Dict[str, str]]:
    log = checked_git(
        root,
        ["log", "--reverse", "--format=%H%x1f%s%x1f%b%x1e", "{}..{}".format(core_commit, feature_commit)],
    )
    records = [record.strip("\n") for record in log.split(RECORD_SEPARATOR)]
    return [commit_record(record) for record in records if record]


def commit_record(record: str) -> Dict[str, str]:
    sha, subject, body = (record.split(FIELD_SEPARATOR, 2) + ["", ""])[:3]
    return {"sha": sha, "subject": subject, "body": body.strip("\n")}


def changed_files(root: str, core_commit: str, feature_commit: str) -> List[str]:
    names = checked_git(
        root,
        ["diff", "--name-only", "-z", "--no-renames", "--ignore-submodules=none", "{}...{}".format(core_commit, feature_commit)],
    )
    return sorted(name for name in names.split("\0") if name)


def merged_pull_requests(root: str, feature: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    command = [
        "gh", "pr", "list",
        "--base", feature,
        "--state", "merged",
        "--json", ",".join(PULL_REQUEST_FIELDS),
        "--limit", "1000",
    ]
    try:
        completed = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    except FileNotFoundError:
        return [], "gh is not installed"
    except OSError as error:
        return [], "gh could not run: {}".format(error.strerror or error)
    if completed.returncode != 0:
        return [], completed.stderr.strip() or "gh exited {}".format(completed.returncode)
    try:
        reported = json.loads(completed.stdout)
    except ValueError:
        return [], "gh printed no JSON"
    if not isinstance(reported, list) or not all(isinstance(entry, dict) for entry in reported):
        return [], "gh printed something other than a list of pull requests"
    return [{field: entry.get(field) for field in PULL_REQUEST_FIELDS} for entry in reported], None
