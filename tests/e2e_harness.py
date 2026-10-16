import json
import os
import secrets
import shutil
import subprocess
import unittest
from typing import Any, Dict, List, Optional, Tuple

from tests import scratch

ROOT = scratch.ROOT
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "held-out")
E2E = os.environ.get("LIGHTHOUSE_E2E") == "1"
CORE = "main"
VARIANTS = ("base", "broken", "clean")


def fixture_ids() -> List[str]:
    return sorted(
        name for name in os.listdir(FIXTURES) if os.path.isfile(os.path.join(FIXTURES, name, "fixture.json"))
    )


def load(fid: str) -> Dict[str, Any]:
    with open(os.path.join(FIXTURES, fid, "fixture.json"), encoding="utf-8") as handle:
        return json.load(handle)


def tree_files(folder: str) -> Dict[str, str]:
    paths = sorted(
        os.path.relpath(os.path.join(parent, name), folder)
        for parent, _, names in os.walk(folder)
        for name in names
    )
    return {path: scratch.read_text(os.path.join(folder, path)) for path in paths}


def state_folder(name: str) -> str:
    return os.path.join(os.path.expanduser("~"), ".lighthouse", name)


def pull_request_answers(fixture: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        fixture["feature"]: [
            {"number": number, "title": pull_request["title"], "body": pull_request["body"]}
            for number, pull_request in enumerate(fixture["pull_requests"], start=1)
        ]
    }


def overlays(fixture: Dict[str, Any], variant: str) -> List[Tuple[str, str, Dict[str, Any]]]:
    if variant == "base":
        return []
    replacements = fixture["clean"] if variant == "clean" else {}
    return [
        (change, replacements.get(change, change), pull_request)
        for change, pull_request in zip(fixture["changes"], fixture["pull_requests"])
    ]


def commit_message(pull_request: Dict[str, Any]) -> str:
    return "{}\n\n{}".format(pull_request["title"], pull_request["body"])


def scratch_repository(test: unittest.TestCase, fid: str, label: str) -> Tuple[str, str, str]:
    root = scratch.temporary_folder(test, "lh-e2e-")
    name = "lh-e2e-{}-{}-{}".format(fid, label, secrets.token_hex(4))
    test.addCleanup(shutil.rmtree, state_folder(name), True)
    remote = os.path.join(root, "remote.git")
    repo = os.path.join(root, name)
    scratch.run_git(root, "init", "-q", "--bare", "--initial-branch=" + CORE, remote)
    scratch.run_git(root, "clone", "-q", remote, repo)
    scratch.run_git(repo, "config", "user.name", "Lighthouse Fixture")
    scratch.run_git(repo, "config", "user.email", "fixture@example.invalid")
    scratch.run_git(repo, "config", "commit.gpgsign", "false")
    scratch.run_git(repo, "symbolic-ref", "HEAD", "refs/heads/" + CORE)
    scratch.commit_files(repo, tree_files(os.path.join(FIXTURES, fid, "base")), "initial version")
    scratch.run_git(repo, "push", "-q", "-u", "origin", CORE)
    return root, repo, remote


def built(root: str, repo: str, remote: str, feature: Optional[str], answers: Dict[str, Any]) -> Dict[str, Any]:
    stub = os.path.join(root, "stub")
    scratch.stub_gh(stub, answers)
    return {
        "repo": repo,
        "remote": remote,
        "core": CORE,
        "feature": feature,
        "stub": stub,
        "env": scratch.environment(os.path.expanduser("~"), stub),
    }


def build(test: unittest.TestCase, fid: str, variant: str) -> Dict[str, Any]:
    if variant not in VARIANTS:
        raise ValueError("variant {} is not one of {}".format(variant, ", ".join(VARIANTS)))
    fixture = load(fid)
    feature = fixture["feature"]
    root, repo, remote = scratch_repository(test, fid, variant)
    if variant != "base":
        scratch.run_git(repo, "checkout", "-q", "-b", feature)
        for change, folder, pull_request in overlays(fixture, variant):
            scratch.run_git(repo, "checkout", "-q", "-b", change, feature)
            scratch.commit_files(repo, tree_files(os.path.join(FIXTURES, fid, folder)), commit_message(pull_request))
            scratch.run_git(repo, "checkout", "-q", feature)
            scratch.run_git(repo, "merge", "-q", "--no-ff", "--no-edit", "-m", pull_request["title"], change)
        scratch.run_git(repo, "push", "-q", "--all", "origin")
        scratch.run_git(repo, "checkout", "-q", CORE)
    return built(root, repo, remote, feature, pull_request_answers(fixture))


def build_single(test: unittest.TestCase, fid: str, change: str) -> Dict[str, Any]:
    fixture = load(fid)
    pull_request = fixture["pull_requests"][fixture["changes"].index(change)]
    root, repo, remote = scratch_repository(test, fid, change)
    scratch.commit_files(repo, tree_files(os.path.join(FIXTURES, fid, change)), commit_message(pull_request))
    scratch.run_git(repo, "push", "-q", "origin", CORE)
    return built(root, repo, remote, None, {})


def run_claude(prompt: str, cwd: str, env: Dict[str, str]) -> Tuple[int, str]:
    completed = subprocess.run(
        [
            "claude", "-p", prompt,
            "--plugin-dir", ROOT,
            "--permission-mode", "bypassPermissions",
            "--output-format", "text",
        ],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout


def parsed_object(line: str) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def last_json_line(text: str) -> Optional[Dict[str, Any]]:
    parsed = (parsed_object(line.strip()) for line in reversed(text.splitlines()) if line.strip())
    return next((value for value in parsed if value is not None), None)
