import json
import os
import secrets
import shutil
import subprocess
import unittest
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tests import scratch

ROOT = scratch.ROOT
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "held-out")
E2E = os.environ.get("LIGHTHOUSE_E2E") == "1"
CORE = "main"
VARIANTS = ("base", "broken", "clean")
MEASURED_VARIANTS = ("broken", "clean")
RUNS = 2
PROMPT = "/lighthouse:test --repo {repo} --core {core} --feature {feature} --results {results}"
PLUGIN_DIR_VARIABLE = "LIGHTHOUSE_E2E_PLUGIN_DIR"
CHILD_RECORD = "child.json"
SEED_HEADING = "Work log of the valley crew, kept by the foreman. Read it through and wait for the next message."
SEED_CLOSING = "Reply only OK."
SEED_LINES = 12000
SEED_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
SEED_NAMES = ("Alma", "Bruno", "Clara", "Dmitri", "Edith", "Felix", "Greta")
SEED_VERBS = (
    "carried", "painted", "mended", "swept", "counted", "washed", "folded", "stacked", "polished", "measured", "repaired",
)
SEED_THINGS = (
    "the lantern", "the ladder", "the kettle", "the fence", "the barrel", "the bench", "the wagon",
    "the blanket", "the bucket", "the shovel", "the basket", "the window", "the rope",
)
SEED_PLACES = (
    "the orchard", "the barn", "the meadow", "the cellar", "the river bank", "the bakery", "the mill", "the hill path",
    "the stable", "the garden", "the porch", "the market", "the bridge", "the pond", "the woodshed", "the chapel",
    "the quarry",
)
SEED_ENDINGS = ("before supper", "after the rain", "at first light")


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


def seed_line(index: int) -> str:
    return "{}: {} {} {} near {}, then {} {} {}.".format(
        SEED_DAYS[index % len(SEED_DAYS)],
        SEED_NAMES[index % len(SEED_NAMES)],
        SEED_VERBS[index % len(SEED_VERBS)],
        SEED_THINGS[index % len(SEED_THINGS)],
        SEED_PLACES[index % len(SEED_PLACES)],
        SEED_VERBS[(index * 3 + 1) % len(SEED_VERBS)],
        SEED_THINGS[(index * 5 + 2) % len(SEED_THINGS)],
        SEED_ENDINGS[index % len(SEED_ENDINGS)],
    )


def seed_text() -> str:
    return "\n".join([SEED_HEADING, *(seed_line(index) for index in range(SEED_LINES)), SEED_CLOSING])


def plugin_folder(plugin_dir: Optional[str] = None) -> str:
    return os.path.abspath(plugin_dir or os.environ.get(PLUGIN_DIR_VARIABLE) or ROOT)


def session_command(plugin: str, prompt: Optional[str] = None, seed_id: Optional[str] = None) -> List[str]:
    asked = [prompt] if prompt is not None else []
    forked = ["--resume", seed_id, "--fork-session"] if seed_id is not None else []
    return [
        "claude", "-p", *asked,
        "--model", "opus",
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--plugin-dir", plugin,
        *forked,
    ]


def run_session(command: List[str], cwd: str, env: Dict[str, str], stdin_text: Optional[str]) -> Dict[str, Any]:
    feed = {"input": stdin_text} if stdin_text is not None else {"stdin": subprocess.DEVNULL}
    completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, **feed)
    return {
        "exit": completed.returncode,
        "output": last_json_line(completed.stdout),
        "transcript": "claude exit {}\n{}\n{}".format(completed.returncode, completed.stdout, completed.stderr),
    }


def number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def fields_of(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def child_dollars(results: Optional[str]) -> float:
    path = os.path.join(results, CHILD_RECORD) if results is not None else None
    if path is None or not os.path.isfile(path):
        return 0.0
    try:
        with open(path, encoding="utf-8") as handle:
            child = json.load(handle)
    except ValueError:
        return 0.0
    return sum(number(cost) for cost in fields_of(fields_of(child).get("cost")).values())


def session_spend(output: Optional[Dict[str, Any]], results: Optional[str]) -> Dict[str, float]:
    fields = fields_of(output)
    return {
        "dollars": number(fields.get("total_cost_usd")) + child_dollars(results),
        "minutes": number(fields.get("duration_ms")) / 60000,
    }


def session_tokens(output: Optional[Dict[str, Any]]) -> Dict[str, int]:
    usage = fields_of(fields_of(output).get("usage"))
    return {
        "input": int(number(usage.get("input_tokens"))),
        "cache_creation": int(number(usage.get("cache_creation_input_tokens"))),
        "cache_read": int(number(usage.get("cache_read_input_tokens"))),
    }


def verdict_line(output: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    result = fields_of(output).get("result")
    return last_json_line(result) if isinstance(result, str) else None


def entry_text(entry: Any) -> str:
    return entry if isinstance(entry, str) else json.dumps(entry)


def names_a_marker(entries: Any, markers: Sequence[str]) -> bool:
    lowered = [marker.lower() for marker in markers]
    listed = entries if isinstance(entries, list) else []
    return any(marker in entry_text(entry).lower() for entry in listed for marker in lowered)


def broken_met(expect: str, markers: Sequence[str], line: Dict[str, Any]) -> bool:
    verdict = line.get("verdict")
    if verdict == "green":
        return False
    if expect == "failures":
        return verdict == "failures" and names_a_marker(line.get("failures"), markers)
    return names_a_marker(line.get("failures"), markers) or names_a_marker(line.get("unproven"), markers)


def clean_met(expect: str, line: Dict[str, Any]) -> bool:
    return (line.get("verdict") == "green") == (expect == "green")


def case_met(variant: str, expect: str, markers: Sequence[str], line: Optional[Dict[str, Any]]) -> bool:
    if line is None:
        return False
    return broken_met(expect, markers, line) if variant == "broken" else clean_met(expect, line)


def case_record(
    fid: str, variant: str, run: int, fixture: Dict[str, Any], output: Optional[Dict[str, Any]], results: Optional[str]
) -> Dict[str, Any]:
    line = verdict_line(output)
    expect = fixture["expect"][variant]
    return {
        "fixture": fid,
        "variant": variant,
        "run": run,
        "expect": expect,
        "line": line,
        "met": case_met(variant, expect, fixture["markers"], line),
        **session_spend(output, results),
    }


def verdict_of(record: Dict[str, Any]) -> Optional[str]:
    return fields_of(record.get("line")).get("verdict")


def score(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    fixtures = sorted({record["fixture"] for record in records})
    return {
        "met": {
            fid: {
                variant: sum(
                    1 for record in records if record["fixture"] == fid and record["variant"] == variant and record["met"]
                )
                for variant in MEASURED_VARIANTS
            }
            for fid in fixtures
        },
        "broken_green": sum(1 for record in records if record["variant"] == "broken" and verdict_of(record) == "green"),
    }


def scored_pass(seed_output: Optional[Dict[str, Any]], records: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "sessions": len(records),
        "minutes": sum(record["minutes"] for record in records),
        "dollars": sum(record["dollars"] for record in records),
        **score(records),
        "seed": {**session_spend(seed_output, None), "tokens": session_tokens(seed_output)},
        "cases": records,
    }


def held_out_cases() -> List[Tuple[str, str, int]]:
    return [
        (fid, variant, run)
        for fid in fixture_ids()
        for variant in MEASURED_VARIANTS
        for run in range(1, RUNS + 1)
    ]


def checkout_state(repo: str) -> Dict[str, str]:
    return {
        "head": scratch.run_git(repo, "rev-parse", "HEAD").strip(),
        "branch": scratch.run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "status": scratch.run_git(repo, "status", "--porcelain"),
    }


def seed_session_id(seed: Dict[str, Any]) -> str:
    session_id = fields_of(seed["output"]).get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("the seed session printed no session_id:\n{}".format(seed["transcript"]))
    return session_id


def measured_case(
    test: unittest.TestCase, case: Tuple[str, str, int], plugin: str, caller: str, seed_id: str
) -> Dict[str, Any]:
    fid, variant, run = case
    fixture = load(fid)
    built = build(test, fid, variant)
    repo = built["repo"]
    results = scratch.temporary_folder(test, "lh-e2e-results-")
    before = checkout_state(repo)
    prompt = PROMPT.format(repo=repo, core=built["core"], feature=built["feature"], results=results)
    session = run_session(session_command(plugin, prompt, seed_id), caller, built["env"], None)
    return {
        **case_record(fid, variant, run, fixture, session["output"], results),
        "exit": session["exit"],
        "transcript": session["transcript"],
        "repo": repo,
        "stub": built["stub"],
        "results": results,
        "before": before,
        "after": checkout_state(repo),
    }


def measured_pass(
    test: unittest.TestCase, cases: Sequence[Tuple[str, str, int]], plugin_dir: Optional[str] = None
) -> Dict[str, Any]:
    plugin = plugin_folder(plugin_dir)
    caller = scratch.temporary_folder(test, "lh-e2e-caller-")
    seed = run_session(session_command(plugin), caller, scratch.environment(os.path.expanduser("~")), seed_text())
    seed_id = seed_session_id(seed)
    records = [measured_case(test, case, plugin, caller, seed_id) for case in cases]
    return {**scored_pass(seed["output"], records), "caller": caller}


def bar_problems(measured: Dict[str, Any], baseline: Dict[str, Any]) -> List[str]:
    green = (
        ["{} broken runs came back green".format(measured["broken_green"])] if measured["broken_green"] else []
    )
    fewer = [
        "{} {} met {} times where the baseline met it {} times".format(fid, variant, have, want)
        for fid, counts in sorted(baseline["met"].items())
        for variant, want in sorted(counts.items())
        for have in [fields_of(measured["met"].get(fid)).get(variant, 0)]
        if have < want
    ]
    slower = (
        ["minutes {} are not below the baseline's {}".format(measured["minutes"], baseline["minutes"])]
        if measured["minutes"] >= baseline["minutes"]
        else []
    )
    dearer = (
        ["dollars {} are not below the baseline's {}".format(measured["dollars"], baseline["dollars"])]
        if measured["dollars"] >= baseline["dollars"]
        else []
    )
    return green + fewer + slower + dearer


def parsed_object(line: str) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def last_json_line(text: str) -> Optional[Dict[str, Any]]:
    parsed = (parsed_object(line.strip()) for line in reversed(text.splitlines()) if line.strip())
    return next((value for value in parsed if value is not None), None)
