import json
import os
import unittest
from unittest import mock

from lighthouse_tool import ledger_import
from tests import scratch

ENVELOPE = ("v", "ts", "plugin", "plugin_version", "kind", "event", "run", "parent", "session", "repo")
CATALOGUE = os.path.join(scratch.ROOT, "lighthouse_tool", "catalogue.json")
SUMMARY_FOLDER = os.path.join("plugin=lighthouse", "kind=summary", "repo=pipeline")

LAUNCH_LINE = (
    '{"run": "/r/pipeline/lighthouse/run-1", "kind": "launch", "time": "2026-10-20T08:00:00.000Z", '
    '"repo": "pipeline", "cost": null, "minutes": 12.5, "keep_awake": true, "priority": "normal", '
    '"verdict": "failures", "reason": null}'
)
VERDICT_LINE = (
    '{"run": "/r/pipeline/lighthouse/run-1", "kind": "verdict", "time": "2026-10-20T08:12:30.000Z", '
    '"repo": "pipeline", "commits": {"core": "1111111111111111111111111111111111111111", '
    '"feature": "2222222222222222222222222222222222222222"}, "verdict": "failures", "reason": null, '
    '"spend": {"input": 100, "cache_write_5m": 200, "cache_write_1h": 0, "cache_read": 3000, "output": 400, '
    '"tokens": 3700, "dollars": 2.4, "messages": 12, "minutes": 12.5, '
    '"models": {"claude-opus-4-1-20250805": {"input": 100, "cache_write_5m": 200, "cache_write_1h": 0, '
    '"cache_read": 3000, "output": 400, "tokens": 3700, "dollars": 2.4}}, "unpriced": [], '
    '"expired_rewrites": {"count": 1, "tokens": 200}, "waiting": {"person": 0, "tool": 4, "model": 8.5}, '
    '"steps": [{"name": "suite", "build": "feature", "minutes": 3, "input": 50, "cache_write_5m": 100, '
    '"cache_write_1h": 0, "cache_read": 1500, "output": 200, "tokens": 1850, "dollars": 1.2}], "paths": []}, '
    '"suite": {"core": {"prepare_minutes": 1, "suite_minutes": 2.5, "rerun_minutes": 0}, '
    '"feature": {"prepare_minutes": 1, "suite_minutes": 2, "rerun_minutes": 0}}, '
    '"paths": [{"name": "checkout total", "kind": "neighbour", "status": "failed", '
    '"check": {"kind": "drive", "evidence": ["drive/checkout.json"]}}]}'
)
RUN_A_LINE = (
    '{"run": "/r/pipeline/lighthouse/run-a", "kind": "verdict", "time": "2026-10-21T09:00:00.000Z", '
    '"repo": "pipeline", "commits": null, "verdict": "green", "reason": null, "spend": null, "suite": null, "paths": []}'
)
RUN_B_LINE = (
    '{"run": "/r/pipeline/lighthouse/run-b", "kind": "verdict", "time": "2026-10-22T10:00:00.000Z", '
    '"repo": "pipeline", "commits": null, "verdict": "blocked", "reason": "the build failed", "spend": null, '
    '"suite": null, "paths": []}'
)
RETEST_LINE = (
    '{"run": "/r/pipeline/lighthouse/retest-1", "kind": "verdict", "time": "2026-10-20T08:00:00.000Z", '
    '"repo": "pipeline", "commits": null, "verdict": "green", "reason": null, "spend": null, "suite": null, '
    '"paths": [{"name": "login", "kind": "changed", "status": "passed", "check": {"kind": "drive"}}, '
    '{"name": "cart", "kind": "neighbour", "status": "passed", "check": {"kind": "drive"}}]}'
)
FIRST_STOP_LINE = (
    '{"run": null, "kind": "verdict", "time": "2026-10-20T08:00:00.100Z", "verdict": "blocked", "reason": "first stop"}'
)
SECOND_STOP_LINE = (
    '{"run": null, "kind": "verdict", "time": "2026-10-20T08:00:00.900Z", "verdict": "blocked", "reason": "second stop"}'
)
LATE_LINE = '{"run": "/r/pipeline/lighthouse/run-late", "kind": "verdict", "time": "2026-10-23T08:00:00.000Z"}\n'
EARLIER_SUMMARY = '{"v":1,"ts":"2026-10-21T09:30:00Z","plugin":"lighthouse","kind":"summary","run":"run-a.20261021T090000Z"}\n'


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def store_files(store):
    return sorted(
        os.path.relpath(os.path.join(folder, name), store) for folder, _, names in os.walk(store) for name in names
    )


def undescribed_keys(label, value, entry):
    if isinstance(value, dict) and "fields" in entry:
        return [
            problem
            for key, item in value.items()
            for problem in (
                undescribed_keys("{}.{}".format(label, key), item, entry["fields"][key])
                if key in entry["fields"]
                else ["{}.{} is not described".format(label, key)]
            )
        ]
    if isinstance(value, list) and "items" in entry:
        return [
            problem
            for index, item in enumerate(value)
            for problem in undescribed_keys("{}[{}]".format(label, index), item, entry["items"])
        ]
    return []


class Imported:
    def __init__(
        self,
        test,
        ledgers,
        store_is_file=False,
        trash_is_file=False,
        store_holds=None,
        trash_holds=None,
        extra_environment=None,
    ):
        self.home = scratch.make_home(test)
        self.state = os.path.join(self.home, ".lighthouse")
        self.trash = os.path.join(self.home, ".Trash")
        scratch_store = scratch.temporary_folder(test, "lh-store-")
        self.store = os.path.join(scratch_store, "store")
        if store_is_file:
            write_text(self.store, "not a folder\n")
        for relative, text in (store_holds or {}).items():
            write_text(os.path.join(self.store, relative), text)
        if trash_is_file:
            write_text(self.trash, "not a folder\n")
        for relative, text in (trash_holds or {}).items():
            write_text(os.path.join(self.trash, relative), text)
        for relative, text in ledgers.items():
            write_text(os.path.join(self.state, relative), text)
        environment = {**scratch.environment(self.home), "PLUGIN_METRICS_DIR": self.store, **(extra_environment or {})}
        self.code, self.stdout, self.stderr = scratch.run_lighthouse(["metrics", "import"], environment)

    def summary(self, run):
        with open(os.path.join(self.store, SUMMARY_FOLDER, run + ".json"), encoding="utf-8") as handle:
            return json.loads(handle.read())

    def trashed(self):
        return sorted(os.listdir(self.trash)) if os.path.isdir(self.trash) else []


def converted_run(test):
    return Imported(
        test,
        {
            os.path.join("pipeline", "runs.jsonl"): LAUNCH_LINE + "\n" + VERDICT_LINE + "\n",
            os.path.join("pipeline", "answers.json"): '{"sign-in": "skip"}\n',
        },
    )


class MetricsImportTest(unittest.TestCase):
    def test_import_converts_a_run(self):
        ran = converted_run(self)
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        self.assertEqual(store_files(ran.store), [os.path.join(SUMMARY_FOLDER, "run-1.20261020T080000Z.json")])
        summary = ran.summary("run-1.20261020T080000Z")
        self.assertEqual(summary["kind"], "summary")
        self.assertEqual(summary["run"], "run-1.20261020T080000Z")
        self.assertEqual(summary["repo"], "pipeline")
        self.assertEqual(summary["started"], "2026-10-20T08:00:00Z")
        self.assertEqual(summary["ended"], "2026-10-20T08:12:30Z")
        self.assertEqual(summary["run_seconds"], 750)
        self.assertEqual(summary["verdict"], "failures")
        self.assertEqual(summary["usd"], 2.4)
        self.assertEqual([step["step"] for step in summary["steps"]], ["suite"])
        self.assertEqual(summary["steps"][0]["elapsed_seconds"], 180)
        self.assertEqual(summary["suite"]["feature"]["suite_seconds"], 120)
        self.assertEqual(
            summary["paths"],
            [{"name": "checkout total", "kind": "neighbour", "status": "failed", "check": "drive", "retry": None, "carried": None}],
        )
        self.assertIsNone(summary["price_date"])
        self.assertEqual(summary["spend_scope"], "results")
        self.assertIs(summary["imported"], True)
        self.assertIn("run-1.20261020T080000Z", ran.stdout)
        self.assertEqual(ran.trashed(), ["runs.jsonl"])

    def test_import_leaves_other_files(self):
        others = {
            "answers.json": '{"sign-in": "skip"}\n',
            "credentials.env": "API_TOKEN=scratch-value\n",
            os.path.join("core-suites", "x.json"): '{"result": "passed"}\n',
        }
        ledger = RUN_A_LINE + "\n"
        ran = Imported(
            self,
            {
                os.path.join("pipeline", "runs.jsonl"): ledger,
                **{os.path.join("pipeline", relative): text for relative, text in others.items()},
            },
        )
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        self.assertEqual(ran.trashed(), ["runs.jsonl"])
        self.assertEqual(read_bytes(os.path.join(ran.trash, "runs.jsonl")), ledger.encode("utf-8"))
        folder = os.path.join(ran.state, "pipeline")
        self.assertTrue(os.path.isdir(folder))
        self.assertFalse(os.path.exists(os.path.join(folder, "runs.jsonl")))
        for relative, text in others.items():
            self.assertEqual(read_bytes(os.path.join(folder, relative)), text.encode("utf-8"))

    def test_import_trashes_an_emptied_folder(self):
        ran = Imported(self, {os.path.join("pipeline", "runs.jsonl"): RUN_A_LINE + "\n"})
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        self.assertEqual(ran.trashed(), ["pipeline", "runs.jsonl"])
        self.assertTrue(os.path.isdir(os.path.join(ran.trash, "pipeline")))
        self.assertFalse(os.path.exists(os.path.join(ran.state, "pipeline")))
        self.assertEqual(len([line for line in ran.stdout.splitlines() if "Trash" in line]), 2)

    def test_import_counts_bad_lines(self):
        ran = Imported(
            self,
            {
                os.path.join("pipeline", "runs.jsonl"): RUN_A_LINE + "\n" + "{not json\n" + RUN_B_LINE + "\n",
                os.path.join("pipeline", "answers.json"): "{}\n",
            },
        )
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        self.assertEqual(
            store_files(ran.store),
            [
                os.path.join(SUMMARY_FOLDER, "run-a.20261021T090000Z.json"),
                os.path.join(SUMMARY_FOLDER, "run-b.20261022T100000Z.json"),
            ],
        )
        skipped = [line for line in ran.stdout.splitlines() if line.startswith("skipped")]
        self.assertEqual(len(skipped), 1)
        self.assertIn("line 2", skipped[0])
        self.assertEqual(ran.trashed(), ["runs.jsonl"])

    def test_import_skips_imported_runs(self):
        earlier = os.path.join(SUMMARY_FOLDER, "run-a.20261021T090000Z.json")
        ran = Imported(
            self,
            {
                os.path.join("pipeline", "runs.jsonl"): RUN_A_LINE + "\n" + RUN_B_LINE + "\n",
                os.path.join("pipeline", "answers.json"): "{}\n",
            },
            store_holds={earlier: EARLIER_SUMMARY},
        )
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        self.assertEqual(store_files(ran.store), [earlier, os.path.join(SUMMARY_FOLDER, "run-b.20261022T100000Z.json")])
        self.assertEqual(read_bytes(os.path.join(ran.store, earlier)), EARLIER_SUMMARY.encode("utf-8"))
        self.assertEqual([line for line in ran.stdout.splitlines() if line.startswith("imported")], ["imported pipeline run-b.20261022T100000Z"])

    def test_import_without_ledger(self):
        ran = Imported(
            self,
            {
                os.path.join("pipeline", "answers.json"): "{}\n",
                os.path.join("interphase", "credentials.env"): "API_TOKEN=scratch-value\n",
            },
        )
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        self.assertEqual(store_files(ran.store), [])
        self.assertFalse(os.path.exists(ran.trash))
        self.assertEqual(read_bytes(os.path.join(ran.state, "pipeline", "answers.json")), b"{}\n")
        self.assertEqual(read_bytes(os.path.join(ran.state, "interphase", "credentials.env")), b"API_TOKEN=scratch-value\n")

    def test_trash_name_collision(self):
        ledger = RUN_A_LINE + "\n"
        ran = Imported(
            self,
            {
                os.path.join("pipeline", "runs.jsonl"): ledger,
                os.path.join("pipeline", "answers.json"): "{}\n",
            },
            trash_holds={"runs.jsonl": "an earlier ledger\n"},
        )
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        self.assertEqual(ran.trashed(), ["runs 2.jsonl", "runs.jsonl"])
        self.assertEqual(read_bytes(os.path.join(ran.trash, "runs 2.jsonl")), ledger.encode("utf-8"))
        self.assertEqual(read_bytes(os.path.join(ran.trash, "runs.jsonl")), b"an earlier ledger\n")

    def test_import_keeps_ledger_when_store_refuses(self):
        ledger = RUN_A_LINE + "\n"
        ran = Imported(self, {os.path.join("pipeline", "runs.jsonl"): ledger}, store_is_file=True)
        self.assertEqual(ran.code, 1, ran.stdout + ran.stderr)
        self.assertIn("metrics not written: ", ran.stdout)
        self.assertEqual(read_bytes(os.path.join(ran.state, "pipeline", "runs.jsonl")), ledger.encode("utf-8"))
        self.assertEqual(ran.trashed(), [])

    def test_import_keeps_ledger_when_trash_fails(self):
        ledger = RUN_A_LINE + "\n"
        ran = Imported(self, {os.path.join("pipeline", "runs.jsonl"): ledger}, trash_is_file=True)
        self.assertEqual(ran.code, 1, ran.stdout + ran.stderr)
        self.assertEqual(ran.summary("run-a.20261021T090000Z")["verdict"], "green")
        self.assertIn("not moved to the Trash", ran.stdout)
        self.assertEqual(read_bytes(os.path.join(ran.state, "pipeline", "runs.jsonl")), ledger.encode("utf-8"))
        self.assertEqual(read_bytes(ran.trash), b"not a folder\n")

    def test_imported_run_has_no_parent(self):
        ran = Imported(
            self,
            {os.path.join("pipeline", "runs.jsonl"): RUN_A_LINE + "\n"},
            extra_environment={"PLUGIN_METRICS_PARENT": "pipeline/feat-x.20261027T000000Z"},
        )
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        self.assertIsNone(ran.summary("run-a.20261021T090000Z")["parent"])

    def test_imported_paths_leave_carried_unknown(self):
        ran = Imported(self, {os.path.join("pipeline", "runs.jsonl"): RETEST_LINE + "\n"})
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        paths = ran.summary("retest-1.20261020T080000Z")["paths"]
        self.assertEqual([path["name"] for path in paths], ["login", "cart"])
        self.assertEqual([path["carried"] for path in paths], [None, None])

    def test_import_keeps_ledger_when_runs_share_an_id(self):
        ledger = FIRST_STOP_LINE + "\n" + SECOND_STOP_LINE + "\n"
        ran = Imported(
            self,
            {
                os.path.join("pipeline", "runs.jsonl"): ledger,
                os.path.join("pipeline", "answers.json"): "{}\n",
            },
        )
        self.assertEqual(ran.code, 1, ran.stdout + ran.stderr)
        self.assertIn("share the run id run.20261020T080000Z", ran.stdout)
        self.assertEqual(store_files(ran.store), [])
        self.assertEqual(read_bytes(os.path.join(ran.state, "pipeline", "runs.jsonl")), ledger.encode("utf-8"))
        self.assertEqual(ran.trashed(), [])

    def test_imported_store_meets_the_catalogue(self):
        ran = converted_run(self)
        self.assertEqual(ran.code, 0, ran.stdout + ran.stderr)
        with open(CATALOGUE, encoding="utf-8") as handle:
            described = json.load(handle)["summary"]["fields"]
        files = store_files(ran.store)
        self.assertNotEqual(files, [])
        for relative in files:
            with open(os.path.join(ran.store, relative), encoding="utf-8") as handle:
                lines = [json.loads(text) for text in handle.read().splitlines()]
            for line in lines:
                problems = [
                    problem
                    for key, value in line.items()
                    if key not in ENVELOPE
                    for problem in (
                        undescribed_keys(key, value, described[key]) if key in described else [key + " is not described"]
                    )
                ]
                self.assertEqual(problems, [], relative)


class Scratch:
    def __init__(self, test, ledgers, trash_holds=None):
        self.home = scratch.make_home(test)
        self.state = os.path.join(self.home, ".lighthouse")
        self.trash = os.path.join(self.home, ".Trash")
        self.store = os.path.join(scratch.temporary_folder(test, "lh-store-"), "store")
        for relative, text in ledgers.items():
            write_text(os.path.join(self.state, relative), text)
        for relative, text in (trash_holds or {}).items():
            write_text(os.path.join(self.trash, relative), text)

    def imported(self):
        environment = {**scratch.base_environment(), "HOME": self.home, "PLUGIN_METRICS_DIR": self.store}
        with mock.patch.dict(os.environ, environment, clear=True):
            return ledger_import.run(["metrics", "import"])


def appending(path, text, then):
    def wrapped(*args, **kwargs):
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
        return then(*args, **kwargs)

    return wrapped


class MetricsImportRaceTest(unittest.TestCase):
    def test_line_appended_during_import_stays_in_place(self):
        place = Scratch(self, {os.path.join("pipeline", "runs.jsonl"): RUN_A_LINE + "\n"})
        ledger = os.path.join(place.state, "pipeline", "runs.jsonl")
        with mock.patch.object(ledger_import, "grouped", appending(ledger, LATE_LINE, ledger_import.grouped)):
            code, _, _ = place.imported()
        self.assertEqual(code, 0)
        self.assertEqual(read_bytes(ledger), LATE_LINE.encode("utf-8"))
        self.assertEqual(read_bytes(os.path.join(place.trash, "runs.jsonl")), (RUN_A_LINE + "\n").encode("utf-8"))

    def test_file_written_before_the_folder_moves_keeps_it(self):
        place = Scratch(self, {os.path.join("pipeline", "runs.jsonl"): RUN_A_LINE + "\n"})
        folder = os.path.join(place.state, "pipeline")
        answers = os.path.join(folder, "answers.json")

        def answering_first(then):
            def wrapped(source, *rest):
                if source == folder:
                    write_text(answers, "{}\n")
                return then(source, *rest)

            return wrapped

        with mock.patch("os.rename", side_effect=answering_first(os.rename)), mock.patch(
            "os.rmdir", side_effect=answering_first(os.rmdir)
        ):
            code, _, _ = place.imported()
        self.assertEqual(code, 0)
        self.assertEqual(read_bytes(answers), b"{}\n")
        self.assertEqual(sorted(os.listdir(place.trash)), ["runs.jsonl"])

    def test_trash_entry_appearing_late_is_never_replaced(self):
        place = Scratch(self, {os.path.join("pipeline", "runs.jsonl"): RUN_A_LINE + "\n", os.path.join("pipeline", "answers.json"): "{}\n"})
        os.makedirs(place.trash)
        earlier = os.path.join(place.trash, "runs.jsonl")
        with mock.patch("os.path.lexists", side_effect=appending(earlier, "an earlier ledger\n", lambda path: False)):
            code, _, _ = place.imported()
        self.assertEqual(code, 0)
        self.assertEqual(read_bytes(earlier), b"an earlier ledger\n")
        self.assertEqual(read_bytes(os.path.join(place.trash, "runs 2.jsonl")), (RUN_A_LINE + "\n").encode("utf-8"))
