import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from tests import scratch

CLAUDE_STUB = """
import json
import os
import sys

CALLS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "claude-calls.jsonl")

stdin_text = sys.stdin.read()
with open(CALLS, "a", encoding="utf-8") as calls:
    calls.write(
        json.dumps(
            {"argv": sys.argv[1:], "cwd": os.getcwd(), "path": os.environ.get("PATH", ""), "stdin": len(stdin_text)}
        )
        + "\\n"
    )
with open(CALLS, encoding="utf-8") as calls:
    count = sum(1 for _ in calls)
line = {"verdict": "green", "failures": [], "unproven": [], "flaky": [], "tokens": 10, "minutes": 1, "dollars": 0.1, "pr": None}
print(
    json.dumps(
        {
            "type": "result",
            "session_id": "s-{}".format(count),
            "total_cost_usd": 0.25,
            "duration_ms": 30000,
            "usage": {
                "input_tokens": 10,
                "cache_creation_input_tokens": 250000,
                "cache_read_input_tokens": 0,
                "output_tokens": 5,
            },
            "result": "the run is done\\n" + json.dumps(line),
        }
    )
)
"""

H1 = {"expect": {"broken": "failures", "clean": "green"}, "markers": ["drop"]}
H6 = {"expect": {"broken": "not-green", "clean": "not-green"}, "markers": ["sheet"]}


def stub_claude(test):
    folder = scratch.temporary_folder(test, "lh-stubs-")
    path = os.path.join(folder, "claude")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("#!" + sys.executable + "\n" + CLAUDE_STUB)
    os.chmod(path, 0o755)
    return folder


def claude_calls(folder):
    with open(os.path.join(folder, "claude-calls.jsonl"), encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def flag_value(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


def write_child(test, cost):
    results = scratch.temporary_folder(test, "lh-results-")
    with open(os.path.join(results, "child.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"session_id": "child-1", "cost": {"claude-opus-5-5": cost}}) + "\n")
    return results


def output_for(line):
    return {"result": "the run is done\n" + json.dumps(line)}


def stubbed_environment(test, stubs, **extra):
    home = scratch.make_home(test)
    return {"HOME": home, "PATH": os.pathsep.join([stubs, os.environ.get("PATH", os.defpath)]), **extra}


class HarnessSpendTest(unittest.TestCase):
    def test_session_spend_adds_the_child_cost(self):
        from tests import e2e_harness

        results = write_child(self, 2.0)
        spend = e2e_harness.session_spend({"total_cost_usd": 1.5, "duration_ms": 60000}, results)

        self.assertEqual(spend["dollars"], 3.5)
        self.assertEqual(spend["minutes"], 1.0)

    def test_harness_uses_the_plugin_dir_override(self):
        from tests import e2e_harness

        stubs = stub_claude(self)
        plugin = scratch.temporary_folder(self, "lh-plugin-")
        with mock.patch.dict(os.environ, stubbed_environment(self, stubs, LIGHTHOUSE_E2E_PLUGIN_DIR=plugin)):
            e2e_harness.measured_pass(self, [("H1", "broken", 1)])

        calls = claude_calls(stubs)
        self.assertEqual(len(calls), 2)
        self.assertEqual([flag_value(call["argv"], "--plugin-dir") for call in calls], [plugin, plugin])

    def test_seed_text_is_fixed_large_and_free_of_markers(self):
        from tests import e2e_harness

        first = e2e_harness.seed_text()
        second = e2e_harness.seed_text()
        fixture_markers = [
            marker for fid in e2e_harness.fixture_ids() for marker in e2e_harness.load(fid)["markers"]
        ]
        leak_markers = [
            line.strip()
            for line in scratch.read_text(os.path.join(e2e_harness.FIXTURES, "LEAK_MARKERS")).splitlines()
            if line.strip()
        ]
        lowered = first.lower()

        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 1000000)
        self.assertTrue(fixture_markers)
        self.assertTrue(leak_markers)
        self.assertEqual([marker for marker in fixture_markers if marker.lower() in lowered], [])
        self.assertEqual([marker for marker in leak_markers if marker.lower() in lowered], [])

    def test_every_case_forks_the_one_seed(self):
        from tests import e2e_harness

        stubs = stub_claude(self)
        with mock.patch.dict(os.environ, stubbed_environment(self, stubs)):
            measured = e2e_harness.measured_pass(self, [("H1", "broken", 1), ("H6", "clean", 1)])

        calls = claude_calls(stubs)
        cases = measured["cases"]
        self.assertEqual(len(calls), 3)
        seed, forks = calls[0], calls[1:]
        self.assertNotIn("--resume", seed["argv"])
        self.assertNotIn("--fork-session", seed["argv"])
        for call, case in zip(forks, cases):
            self.assertEqual(flag_value(call["argv"], "--resume"), "s-1")
            self.assertIn("--fork-session", call["argv"])
            self.assertEqual(call["path"].split(os.pathsep)[0], case["stub"])
        self.assertNotEqual(cases[0]["stub"], cases[1]["stub"])
        self.assertEqual([flag_value(call["argv"], "--model") for call in calls], ["opus", "opus", "opus"])
        self.assertEqual(len({flag_value(call["argv"], "--plugin-dir") for call in calls}), 1)
        folders = {call["cwd"] for call in calls}
        self.assertEqual(len(folders), 1)
        folder = folders.pop()
        self.assertEqual(os.listdir(folder), [])
        self.assertFalse(folder == scratch.ROOT or folder.startswith(scratch.ROOT + os.sep))

    def test_pass_totals_leave_the_seed_out(self):
        from tests import e2e_harness

        seed_output = {"total_cost_usd": 2.0, "duration_ms": 60000}
        records = [
            e2e_harness.case_record(
                fid, "broken", 1, fixture, {"total_cost_usd": 1.0, "duration_ms": 120000}, write_child(self, 0.5)
            )
            for fid, fixture in (("H1", H1), ("H6", H6))
        ]
        measured = e2e_harness.scored_pass(seed_output, records)

        self.assertEqual(measured["dollars"], 3.0)
        self.assertEqual(measured["minutes"], 4.0)
        self.assertEqual(measured["seed"]["dollars"], 2.0)
        self.assertEqual(measured["seed"]["minutes"], 1.0)

    def test_a_case_is_met_by_its_fixtures_expect(self):
        from tests import e2e_harness

        lines = [
            ("H1", H1, "broken", {"verdict": "failures", "failures": ["add a drop command"]}),
            ("H1", H1, "broken", {"verdict": "unproven", "unproven": ["drop a trip"]}),
            ("H6", H6, "broken", {"verdict": "failures", "failures": ["print a sheet of labels"]}),
            ("H6", H6, "broken", {"verdict": "unproven", "unproven": ["Sheet on the printer"]}),
            ("H1", H1, "broken", {"verdict": "green"}),
            ("H1", H1, "clean", {"verdict": "green"}),
            ("H6", H6, "clean", {"verdict": "green"}),
        ]
        records = [
            e2e_harness.case_record(fid, variant, run, fixture, output_for(line), None)
            for run, (fid, fixture, variant, line) in enumerate(lines, start=1)
        ]
        scored = e2e_harness.score(records)

        self.assertEqual(scored["met"]["H1"]["broken"], 1)
        self.assertEqual(scored["met"]["H6"]["broken"], 2)
        self.assertEqual(scored["broken_green"], 1)
        self.assertEqual(scored["met"]["H1"]["clean"], 1)
        self.assertEqual(scored["met"]["H6"]["clean"], 0)

    def test_held_out_bar_holds_against_the_baseline(self):
        from tests import e2e_harness

        measured = {
            "broken_green": 0,
            "minutes": 50,
            "dollars": 40,
            "met": {"H1": {"broken": 2, "clean": 2}, "H6": {"broken": 1, "clean": 0}},
        }
        baseline = {
            "broken_green": 0,
            "minutes": 60,
            "dollars": 50,
            "met": {"H1": {"broken": 2, "clean": 1}, "H6": {"broken": 1, "clean": 0}},
        }
        failing = {
            "broken_green is 1": {**measured, "broken_green": 1},
            "H1 broken is met once": {**measured, "met": {**measured["met"], "H1": {"broken": 1, "clean": 2}}},
            "H6 broken is met never": {**measured, "met": {**measured["met"], "H6": {"broken": 0, "clean": 0}}},
            "minutes is 60": {**measured, "minutes": 60},
            "dollars is 50": {**measured, "dollars": 50},
        }

        self.assertEqual(e2e_harness.bar_problems(measured, baseline), [])
        for label, worse in failing.items():
            with self.subTest(label):
                self.assertEqual(len(e2e_harness.bar_problems(worse, baseline)), 1)

    def test_measure_script_writes_the_baseline(self):
        stubs = stub_claude(self)
        plugin = scratch.temporary_folder(self, "lh-plugin-")
        out = os.path.join(scratch.temporary_folder(self, "lh-baseline-"), "baseline.json")
        env = scratch.environment(scratch.make_home(self), stubs)
        completed = subprocess.run(
            [sys.executable, "-m", "tests.measure_held_out", "--plugin-dir", plugin, "--commit", "abc", "--out", out],
            cwd=scratch.ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        baseline = json.loads(scratch.read_text(out))
        self.assertEqual(baseline["commit"], "abc")
        self.assertEqual(baseline["sessions"], 24)
        for key in ("minutes", "dollars", "broken_green"):
            self.assertIn(key, baseline)
        self.assertEqual(sorted(baseline["met"]), ["H1", "H2", "H3", "H4", "H5", "H6"])
        for counts in baseline["met"].values():
            self.assertEqual(sorted(counts), ["broken", "clean"])
            self.assertTrue(all(isinstance(count, int) for count in counts.values()))
        self.assertEqual(sorted(baseline["seed"]), ["dollars", "minutes", "tokens"])


if __name__ == "__main__":
    unittest.main()
