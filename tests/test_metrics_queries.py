import datetime
import glob
import json
import os
import re
import subprocess
import unittest

from tests import scratch
from tests.test_launch import GREEN_LINE, claude_output
from tests.test_run_record import Launched, green_plan, marked_child

DUCKDB_URL = "https://github.com/duckdb/duckdb/releases/download/v2.0.0/duckdb-cli-linux-amd64.tar.gz"
QUERY_COLUMNS = {
    "verdicts": ["verdict", "runs"],
    "spend": ["run", "usd", "run_seconds"],
    "steps": ["step", "elapsed_seconds", "usd"],
    "paths": ["kind", "status", "check", "paths"],
    "suite": ["build", "suite_seconds", "reused"],
    "blocked": ["reason", "runs"],
}
VIEW_PARTS = (("events", "event", ".jsonl"), ("summaries", "summary", ".json"))
IMPORTED_SUMMARY = {
    "started": "2026-09-01T10:00:00Z",
    "ended": "2026-09-01T10:20:00Z",
    "run_seconds": 1200,
    "verdict": "green",
    "reason": None,
    "core": None,
    "feature": None,
    "core_commit": "a" * 40,
    "feature_commit": "b" * 40,
    "retest": None,
    "final": None,
    "spec": None,
    "failures": 0,
    "unproven": 0,
    "flaky": 0,
    "build": None,
    "suite": None,
    "paths": [{"name": "opens the report", "kind": "new", "status": "passed", "check": "drive", "retry": None, "carried": None}],
    "usd": 0.75,
    "price_date": None,
    "tokens": None,
    "messages": None,
    "models": None,
    "unpriced": None,
    "steps": None,
    "drives": None,
    "shared": None,
    "caller": None,
    "waiting": None,
    "expired_rewrites": None,
    "child_exit": None,
    "child_session": None,
    "results": "/results/one",
    "spend_scope": "results",
    "imported": True,
}


def skill_blocks():
    return re.findall(r"```sql\n(.*?)```", scratch.read_text(scratch.skill_path("metrics")), re.DOTALL)


def view_block(name, empty):
    return next(
        block
        for block in skill_blocks()
        if block.startswith("CREATE VIEW {} AS".format(name)) and ("WHERE false" in block) == empty
    )


def stored_files(root, kind, suffix):
    return glob.glob(os.path.join(root, "plugin=lighthouse", "kind=" + kind, "**", "*" + suffix), recursive=True)


def views(root):
    session = next(block for block in skill_blocks() if block.startswith("SET TimeZone"))
    defined = [
        view_block(name, not stored_files(root, kind, suffix)).replace("<root>", root) for name, kind, suffix in VIEW_PARTS
    ]
    return session + "".join(defined)


def named_queries():
    with open(os.path.join(scratch.ROOT, "lighthouse_tool", "catalogue.json"), encoding="utf-8") as handle:
        return {query["name"]: query["sql"] for query in json.load(handle)["queries"]}


def duckdb(test, root, sql):
    completed = subprocess.run(
        ["duckdb", "-json"],
        input=views(root) + sql + ";\n",
        env={**scratch.base_environment(), "HOME": scratch.make_home(test)},
        capture_output=True,
        text=True,
    )
    rows = json.loads(completed.stdout) if completed.returncode == 0 and completed.stdout.strip() else []
    return completed.returncode, rows, completed.stderr


def launched_store(test):
    store = scratch.temporary_folder(test, "lh-store-")
    home = scratch.make_home(test)
    results = os.path.join(scratch.temporary_folder(test, "lh-results-"), "results")
    plan = {**green_plan(home, "s-green"), "child": marked_child(results), "output": claude_output(GREEN_LINE)}
    green = Launched(test, plan, home=home, results=results, env={"CLAUDE_CODE_SESSION_ID": "s-green"}, store=store)
    test.assertEqual(green.code, 0, green.stderr)
    repo, _ = scratch.make_repo(test)
    refused = Launched(test, {"output": claude_output(GREEN_LINE)}, repo=repo, results=os.path.join(repo, "results"), store=store)
    test.assertEqual(refused.code, 2, refused.stderr)
    return store


def written_summary(test, store, plugin, fields):
    from lighthouse_tool import metrics_writer

    start = datetime.datetime(2026, 9, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    environ = {"HOME": scratch.make_home(test), "PLUGIN_METRICS_DIR": store}
    run = metrics_writer.run_id("feat-x", start)
    test.assertIsNone(metrics_writer.write_summary(plugin, "0.3.0", "work", run, fields, environ=environ, now=start))


class MetricsQueriesTest(unittest.TestCase):
    def test_named_queries_run(self):
        store = launched_store(self)
        queries = named_queries()
        self.assertEqual(sorted(queries), sorted(QUERY_COLUMNS))
        for name, columns in QUERY_COLUMNS.items():
            with self.subTest(query=name):
                code, rows, stderr = duckdb(self, store, queries[name])
                self.assertEqual(code, 0, stderr)
                self.assertTrue(rows, name)
                for row in rows:
                    self.assertEqual([column for column in columns if column not in row], [], row)

    def test_queries_count_only_lighthouse(self):
        store = launched_store(self)
        written_summary(self, store, "pipeline", {"started": "2026-09-01T10:00:00Z", "verdict": "green", "reason": None})
        code, rows, stderr = duckdb(self, store, named_queries()["verdicts"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(sum(row["runs"] for row in rows), 2)

    def test_queries_run_without_events(self):
        store = scratch.temporary_folder(self, "lh-store-")
        written_summary(self, store, "lighthouse", IMPORTED_SUMMARY)
        self.assertEqual(stored_files(store, "event", ".jsonl"), [])
        for name, sql in named_queries().items():
            with self.subTest(query=name):
                code, rows, stderr = duckdb(self, store, sql)
                self.assertEqual(code, 0, stderr)
                if name == "verdicts":
                    self.assertEqual(rows, [{"verdict": "green", "runs": 1}])

    def test_ci_pins_duckdb(self):
        workflow = scratch.read_text(os.path.join(scratch.ROOT, ".github", "workflows", "ci.yml"))
        job = workflow.split("\n  test:\n", 1)[1].split("\n  validate:\n", 1)[0]
        self.assertIn(DUCKDB_URL, job)
        self.assertLess(job.index(DUCKDB_URL), job.index("python -m unittest discover tests"))


if __name__ == "__main__":
    unittest.main()
