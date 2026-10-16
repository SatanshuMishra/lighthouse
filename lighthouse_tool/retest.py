import argparse
import json
import os
import posixpath
import shutil
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool import repo as repository
from lighthouse_tool import suite, verdict
from lighthouse_tool.change import changed_files
from lighthouse_tool.repo import Parser, Refusal, require_root

RETEST = verdict.RETEST
CARRIED_FOLDER = verdict.CARRIED_FOLDER
BLOCKED = "blocked"
PASSED = "passed"
RETESTED_STATUSES = ("failed", "unproven")


def parser() -> Parser:
    arguments = Parser(prog="lighthouse retest", add_help=False)
    for flag in ("--previous", "--results", "--repo", "--core", "--feature", "--profile"):
        arguments.add_argument(flag, required=True)
    return arguments


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        plan = retest_command(options)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse retest: {}".format(refusal)
    return 0, json.dumps(plan), None


def retest_command(options: argparse.Namespace) -> Dict[str, Any]:
    previous = os.path.realpath(options.previous)
    results = os.path.realpath(options.results)
    if previous == results:
        raise Refusal("the --previous and --results folders must differ; give the new run its own results folder")
    root = require_root(options.repo)
    findings = previous_findings(previous)
    commits = previous_commits(previous)
    surfaces = profile_surfaces(root, options.profile)
    tips = {"core": suite.resolved(root, options.core), "feature": suite.resolved(root, options.feature)}
    plan = planned(root, findings, commits, tips, surfaces)
    carried = [path for path in findings["paths"] if path["name"] in plan["carried"]]
    sources = carried_sources(previous, carried)
    os.makedirs(results, exist_ok=True)
    copy_evidence(results, sources)
    write_record(results, {**plan, "previous": previous, "carried_paths": [carried_entry(path) for path in carried]})
    return plan


def previous_findings(previous: str) -> Dict[str, Any]:
    try:
        return verdict.read_findings(previous)
    except Refusal as refusal:
        raise Refusal("the previous {} is unusable: {}".format(verdict.FINDINGS, refusal))


def previous_commits(previous: str) -> Dict[str, str]:
    try:
        with open(os.path.join(previous, suite.COMMITS), encoding="utf-8") as handle:
            commits = json.load(handle)
    except (OSError, ValueError):
        raise Refusal("the previous folder {} has no readable {}".format(previous, suite.COMMITS))
    if not isinstance(commits, dict) or not all(isinstance(commits.get(build), str) for build in suite.BUILDS):
        raise Refusal("the previous {} must be an object holding core and feature commits".format(suite.COMMITS))
    return {build: commits[build] for build in suite.BUILDS}


def profile_surfaces(root: str, path: str) -> List[Dict[str, Any]]:
    profile = repository.load_profile(root, path)
    if not isinstance(profile, dict):
        raise Refusal("profile {} is missing or not a JSON object".format(path))
    surfaces = profile.get("surfaces")
    if not isinstance(surfaces, list):
        raise Refusal("profile {} records no surfaces list".format(path))
    return [surface for surface in surfaces if isinstance(surface, dict) and isinstance(surface.get("name"), str)]


def needs_full_retest(root: str, findings: Dict[str, Any], commits: Dict[str, str], tips: Dict[str, str]) -> bool:
    core_moved = commits["core"] != tips["core"]
    ancestry, _, _ = repository.git(root, ["merge-base", "--is-ancestor", commits["feature"], tips["feature"]])
    proved_nothing = BLOCKED in (findings["suite"]["result"], findings["build"]["result"]) or not findings["paths"]
    return core_moved or ancestry != 0 or proved_nothing


def planned(
    root: str,
    findings: Dict[str, Any],
    commits: Dict[str, str],
    tips: Dict[str, str],
    surfaces: List[Dict[str, Any]],
) -> Dict[str, Any]:
    paths = findings["paths"]
    if needs_full_retest(root, findings, commits, tips):
        return {"full": True, "changed": [], "retest": [path["name"] for path in paths], "surfaces": [], "carried": []}
    changed = changed_files(root, commits["feature"], tips["feature"])
    touched = [surface["name"] for surface in surfaces if is_touched(surface, changed)]
    return {
        "full": False,
        "changed": changed,
        "retest": [path["name"] for path in paths if path["status"] in RETESTED_STATUSES],
        "surfaces": touched,
        "carried": [path["name"] for path in paths if path["status"] == PASSED and path["surface"] not in touched],
    }


def is_touched(surface: Dict[str, Any], changed: List[str]) -> bool:
    spelled = surface.get("paths")
    surface_paths = [path for path in spelled if isinstance(path, str)] if isinstance(spelled, list) else []
    return any(covers(posixpath.normpath(path), changed) for path in surface_paths)


def covers(normal: str, changed: List[str]) -> bool:
    return normal == "." or any(name == normal or name.startswith(normal + "/") for name in changed)


def carried_entry(path: Dict[str, Any]) -> Dict[str, Any]:
    return {**path, "evidence": [CARRIED_FOLDER + "/" + posixpath.normpath(item) for item in path["evidence"]]}


def carried_sources(previous: str, carried: List[Dict[str, Any]]) -> Dict[str, str]:
    items = [item for path in carried for item in path["evidence"]]
    return {posixpath.normpath(item): evidence_source(previous, item) for item in items}


def evidence_source(previous: str, item: str) -> str:
    normal = posixpath.normpath(item)
    if os.path.isabs(item) or normal == ".." or normal.startswith("../"):
        raise Refusal("carried evidence {} must be a relative path inside the previous folder".format(item))
    source = os.path.realpath(os.path.join(previous, normal))
    if os.path.commonpath([previous, source]) != previous or not os.path.isfile(source):
        raise Refusal("carried evidence {} is not a file in the previous folder {}".format(item, previous))
    return source


def copy_evidence(results: str, sources: Dict[str, str]) -> None:
    for item, source in sources.items():
        destination = os.path.join(results, CARRIED_FOLDER, item)
        try:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copyfile(source, destination)
        except (OSError, shutil.Error) as error:
            raise Refusal("cannot copy carried evidence {}: {}".format(item, error))


def write_record(results: str, record: Dict[str, Any]) -> None:
    with open(os.path.join(results, RETEST), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, indent=2) + "\n")
