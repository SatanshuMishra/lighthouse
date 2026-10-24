import json
import os
import unittest

from tests import scratch


def write_ledger(home, lines):
    folder = os.path.join(home, ".lighthouse", "work")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "runs.jsonl"), "w", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(line) + "\n" for line in lines))


def runs_of(test, home):
    repo, _ = scratch.make_repo(test)
    code, stdout, stderr = scratch.run_lighthouse(["runs", "--repo", repo], scratch.environment(home))
    test.assertEqual(code, 0, stderr)
    return json.loads(stdout.strip().splitlines()[-1])


class RunsTest(unittest.TestCase):
    def test_runs_summarises_the_ledger(self):
        home = scratch.make_home(self)
        write_ledger(
            home,
            [
                {"run": "/results/one", "kind": "verdict", "verdict": "green", "spend": {"tokens": 100, "minutes": 10, "dollars": 1.0}},
                {"run": "/results/two", "kind": "verdict", "verdict": "failures", "spend": {"tokens": 300, "minutes": 30, "dollars": 3.0}},
            ],
        )
        summary = runs_of(self, home)
        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["minutes"]["total"], 40)
        self.assertEqual(summary["minutes"]["median"], 20)
        self.assertEqual(summary["dollars"]["total"], 4.0)
        self.assertEqual(summary["dollars"]["median"], 2.0)

    def test_runs_on_an_empty_ledger(self):
        summary = runs_of(self, scratch.make_home(self))
        self.assertEqual(summary["runs"], 0)

    def test_runs_prefers_the_reported_cost(self):
        home = scratch.make_home(self)
        write_ledger(
            home,
            [
                {"run": "/results/one", "kind": "verdict", "verdict": "green", "spend": {"tokens": 100, "minutes": 10, "dollars": 1.0}},
                {"run": "/results/one", "kind": "launch", "cost": 1.4, "minutes": 11, "verdict": "green"},
            ],
        )
        summary = runs_of(self, home)
        self.assertEqual(summary["runs"], 1)
        self.assertEqual(summary["dollars"]["total"], 1.4)

    def test_runs_sums_kinds_steps_waits_and_rewrites(self):
        home = scratch.make_home(self)
        spend = {
            "input": 5, "cache_write_5m": 6, "cache_write_1h": 7, "cache_read": 8, "output": 9, "tokens": 35,
            "minutes": 4, "dollars": 0.1,
            "steps": [{"name": "suite", "build": None, "minutes": 2.5}],
            "waiting": {"person": 1.5, "tool": 1, "model": 1},
            "expired_rewrites": {"count": 1, "tokens": 6},
        }
        write_ledger(
            home,
            [
                {"run": "/results/one", "kind": "verdict", "spend": spend},
                {"run": "/results/two", "kind": "verdict", "spend": spend},
            ],
        )
        summary = runs_of(self, home)
        self.assertEqual(summary["tokens"], {"input": 10, "cache_write_5m": 12, "cache_write_1h": 14, "cache_read": 16, "output": 18, "tokens": 70})
        self.assertEqual(summary["steps"], {"suite": 5.0})
        self.assertEqual(summary["waiting_on_person"], 3.0)
        self.assertEqual(summary["expired_rewrites"], {"count": 2, "tokens": 12})


if __name__ == "__main__":
    unittest.main()
