import json
import os
import shlex
import unittest
from typing import Any, Dict, List

from tests import e2e_harness, scratch, test_fixtures

RETIRED_MARKERS = (
    "jotbook",
    "JOTBOOK_FILE",
    "notes_file",
    "--notebook",
    "--store",
    "note-search",
    "pantry-add",
    "pantry-submit",
    "pantry-item",
    "pantry-items",
    "pantry-count",
    "pantry-form",
    "pantry-quick-picks",
    "quick-picks",
    "setupQuickPicks",
    "setupList",
    "shelfapi",
    "/loan-notices",
    "/loans",
    "/books",
    "format_day",
    "list_notices",
    "list_loans",
    "list_books",
    "readable_day",
    "tillkit",
    "line_total",
    "tax_on",
    "add_tax",
    "basket_summary",
    "wholesale-and-basket",
    "greenhand",
    "houseplant-care",
    "seed-sowing",
    "leaf-pest-check",
    "leaf-pests",
    "hearthctl",
    "HEARTH_PORT",
    "usbmodem-hearth",
    "BOOST_SECONDS",
    "start_boost",
)

KEY_TYPES = (
    ("kind", str),
    ("feature", str),
    ("suite", str),
    ("changes", list),
    ("clean", dict),
    ("pull_requests", list),
    ("markers", list),
    ("surfaces", list),
    ("expect", dict),
)
STRING_LIST_KEYS = ("changes", "markers", "surfaces")
CHANGES = ["change-1", "change-2"]
FAILURES = {"broken": "failures", "clean": "green"}
NOT_GREEN = {"broken": "not-green", "clean": "not-green"}
PROFILE = os.path.join(".lighthouse", "profile.json")
PROBE = "probe.sh"
PROBE_PASSES = {"broken": False, "clean": True}


def retired_markers_in(folder: str) -> List[str]:
    lowered = {path: text.lower() for path, text in e2e_harness.tree_files(folder).items()}
    return [
        "{} holds {}".format(path, marker)
        for path, marker in sorted(
            (path, marker) for path, text in lowered.items() for marker in RETIRED_MARKERS if marker.lower() in text
        )
    ]


def key_problems(fixture: Dict[str, Any]) -> List[str]:
    expected = [key for key, _ in KEY_TYPES]
    missing = ["fixture.json lacks the key {}".format(key) for key in expected if key not in fixture]
    extra = ["fixture.json holds the unexpected key {}".format(key) for key in sorted(fixture) if key not in expected]
    return missing + extra


def wrong_type(fixture: Dict[str, Any], key: str, kind: type) -> bool:
    value = fixture[key]
    if not isinstance(value, kind):
        return True
    return key in STRING_LIST_KEYS and not all(isinstance(item, str) for item in value)


def type_problems(fixture: Dict[str, Any]) -> List[str]:
    return [
        "{} is not a {}{}".format(key, kind.__name__, " of strings" if key in STRING_LIST_KEYS else "")
        for key, kind in KEY_TYPES
        if key in fixture and wrong_type(fixture, key, kind)
    ]


def well_typed(fixture: Dict[str, Any], key: str) -> bool:
    return key in fixture and not wrong_type(fixture, key, dict(KEY_TYPES)[key])


def changes_problems(fixture: Dict[str, Any]) -> List[str]:
    if not well_typed(fixture, "changes") or fixture["changes"] == CHANGES:
        return []
    return ["changes is {} where it must be {}".format(json.dumps(fixture["changes"]), json.dumps(CHANGES))]


def clean_problems(fixture: Dict[str, Any]) -> List[str]:
    if not well_typed(fixture, "clean") or any(fixture["clean"] == {change: "clean"} for change in CHANGES):
        return []
    return ["clean is {} where it must map exactly one of change-1 and change-2 to clean".format(json.dumps(fixture["clean"]))]


def described(pull_request: Any) -> bool:
    return isinstance(pull_request, dict) and all(
        isinstance(pull_request.get(field), str) and pull_request.get(field).strip() for field in ("title", "body")
    )


def pull_request_problems(fixture: Dict[str, Any]) -> List[str]:
    if not well_typed(fixture, "pull_requests"):
        return []
    pull_requests = fixture["pull_requests"]
    count = [] if len(pull_requests) == 2 else ["pull_requests holds {} entries where it must hold two".format(len(pull_requests))]
    undescribed = [
        "pull_requests entry {} lacks a title or a body".format(number)
        for number, pull_request in enumerate(pull_requests, start=1)
        if not described(pull_request)
    ]
    return count + undescribed


def empty_problems(fixture: Dict[str, Any]) -> List[str]:
    return ["{} is empty".format(key) for key in ("markers", "surfaces") if well_typed(fixture, key) and not fixture[key]]


def expect_problems(fixture: Dict[str, Any]) -> List[str]:
    if not well_typed(fixture, "expect") or fixture["expect"] in (FAILURES, NOT_GREEN):
        return []
    return [
        "expect is {} where it must be {} or {}".format(
            json.dumps(fixture["expect"]), json.dumps(FAILURES), json.dumps(NOT_GREEN)
        )
    ]


def schema_problems(fixture: Dict[str, Any]) -> List[str]:
    return (
        key_problems(fixture)
        + type_problems(fixture)
        + changes_problems(fixture)
        + clean_problems(fixture)
        + pull_request_problems(fixture)
        + empty_problems(fixture)
        + expect_problems(fixture)
    )


def parsed_profile(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except ValueError:
        return None


def device_profile_problems(profile: Any) -> List[str]:
    fields = profile if isinstance(profile, dict) else {}
    surfaces = fields.get("surfaces") if isinstance(fields.get("surfaces"), list) else []
    unavailable = [surface for surface in surfaces if isinstance(surface, dict) and surface.get("available") is False]
    available = [] if unavailable else ["no surface of the base profile has available false"]
    off_limits = [] if fields.get("off_limits") else ["the base profile's off_limits is empty"]
    return available + off_limits


def profile_problems(folder: str, fixture: Dict[str, Any]) -> List[str]:
    path = os.path.join(folder, "base", PROFILE)
    expect = fixture.get("expect")
    if expect == FAILURES:
        return ["base holds {} although this fixture must start without a profile".format(PROFILE)] if os.path.exists(path) else []
    if expect != NOT_GREEN:
        return []
    profile = parsed_profile(path) if os.path.isfile(path) else None
    if profile is None:
        return ["base {} is missing or not JSON".format(PROFILE)]
    return device_profile_problems(profile)


def probe_run_problem(label: str, code: int, output: str) -> List[str]:
    if (code == 0) == PROBE_PASSES[label]:
        return []
    return ["{} exits {} on the {} checkout: {}".format(PROBE, code, label, output.strip())]


def probe_problems(test: unittest.TestCase, fid: str, folder: str, fixture: Dict[str, Any]) -> List[str]:
    probe = os.path.join(folder, PROBE)
    expect = fixture.get("expect")
    if expect == NOT_GREEN:
        return ["{} holds {} although a not-green fixture holds no probe".format(fid, PROBE)] if os.path.exists(probe) else []
    if expect != FAILURES:
        return []
    if not os.path.isfile(probe):
        return ["{} lacks {}".format(fid, PROBE)]
    env = {**scratch.environment(scratch.make_home(test)), "PYTHONDONTWRITEBYTECODE": "1"}
    command = "sh " + shlex.quote(os.path.abspath(probe))
    runs = [
        (label, scratch.run_shell(command, checkout["repo"], env, test_fixtures.SUITE_TIMEOUT_SECONDS))
        for label, checkout in test_fixtures.checkouts(test, fid)
        if label in PROBE_PASSES
    ]
    return [problem for label, (code, output) in runs for problem in probe_run_problem(label, code, output)]


def fixture_problems(test: unittest.TestCase, fid: str, kind: str) -> List[str]:
    folder = os.path.join(e2e_harness.FIXTURES, fid)
    fixture = e2e_harness.load(fid)
    kinds = [] if fixture.get("kind") == kind else ["kind is {} where it must be {}".format(json.dumps(fixture.get("kind")), json.dumps(kind))]
    return (
        kinds
        + schema_problems(fixture)
        + retired_markers_in(folder)
        + profile_problems(folder, fixture)
        + probe_problems(test, fid, folder, fixture)
    )
