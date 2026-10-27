import json
import os
import unittest

from tests import scratch


def metrics_environment(test, home):
    store = scratch.temporary_folder(test, "lh-store-")
    return store, {**scratch.environment(home), "PLUGIN_METRICS_DIR": store}


def write_summary(store, repo_folder, run, fields):
    from lighthouse_tool import metrics_writer

    warning = metrics_writer.write_summary(
        "lighthouse", "0.3.0", repo_folder, run, fields, environ={"PLUGIN_METRICS_DIR": store, "HOME": store}
    )
    assert warning is None, warning


def runs_of(test, repo, env):
    code, stdout, stderr = scratch.run_lighthouse(["runs", "--repo", repo], env)
    test.assertEqual(code, 0, stderr)
    return json.loads(stdout.strip().splitlines()[-1])


class RunsTest(unittest.TestCase):
    def test_runs_reads_summaries(self):
        home = scratch.make_home(self)
        store, env = metrics_environment(self, home)
        repo, _ = scratch.make_repo(self)
        folder = os.path.basename(repo)
        write_summary(
            store, folder, "run-one",
            {"run_seconds": 600, "usd": 1.5, "steps": [{"step": "suite", "build": None, "elapsed_seconds": 120}]},
        )
        write_summary(
            store, folder, "run-two",
            {"run_seconds": 1200, "usd": None, "steps": [{"step": "suite", "build": None, "elapsed_seconds": 240}]},
        )
        summary = runs_of(self, repo, env)
        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["minutes"], {"total": 30, "median": 15})
        self.assertEqual(summary["dollars"], {"total": 1.5, "median": 1.5})
        self.assertEqual(summary["steps"], {"suite": 6.0})

    def test_runs_ignores_the_ledger(self):
        home = scratch.make_home(self)
        _, env = metrics_environment(self, home)
        folder = os.path.join(home, ".lighthouse", "work")
        os.makedirs(folder)
        with open(os.path.join(folder, "runs.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(line) + "\n" for line in [
                {"run": "/results/one", "kind": "verdict", "spend": {"minutes": 10, "dollars": 1.0}},
                {"run": "/results/two", "kind": "verdict", "spend": {"minutes": 30, "dollars": 3.0}},
            ]))
        repo, _ = scratch.make_repo(self)
        self.assertEqual(runs_of(self, repo, env)["runs"], 0)

    def test_runs_reads_only_its_repository(self):
        home = scratch.make_home(self)
        store, env = metrics_environment(self, home)
        repo, _ = scratch.make_repo(self)
        write_summary(store, os.path.basename(repo), "run-one", {"run_seconds": 600})
        write_summary(store, "another-repository", "run-two", {"run_seconds": 1200})
        self.assertEqual(runs_of(self, repo, env)["runs"], 1)


if __name__ == "__main__":
    unittest.main()
