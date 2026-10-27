import datetime
import json
import os
import unittest
from unittest import mock

from tests import scratch

FIXTURES = os.path.join(scratch.ROOT, "metrics", "fixtures")
LINE_SCHEMA = os.path.join(scratch.ROOT, "metrics", "schema", "line.schema.json")
WARNING_PREFIX = "metrics not written: "
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
ENVELOPE = ["v", "ts", "plugin", "plugin_version", "kind", "event", "run", "parent", "session", "repo"]


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return json.load(handle)


def moment(text):
    return datetime.datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=datetime.timezone.utc)


def substituted(value, root, home):
    return {"<root>": root, "<home>": home}.get(value, value) if isinstance(value, str) else value


def relative(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def reported(result, root):
    if isinstance(result, tuple):
        return [relative(path, root) for path in result]
    if isinstance(result, str) and result.startswith(WARNING_PREFIX):
        subject = result[len(WARNING_PREFIX):]
        return WARNING_PREFIX + subject[:subject.index(": ") + 2]
    return result


def call_result(writer, call, environ, root, home):
    args = {name: substituted(value, root, home) for name, value in call["args"].items()}
    if call["fn"] in ("append_event", "write_summary"):
        return getattr(writer, call["fn"])(environ=environ, now=moment(call["now"]), **args)
    if call["fn"] == "write_catalogue":
        return writer.write_catalogue(environ=environ, **args)
    if call["fn"] == "prune":
        return writer.prune(**args)
    return writer.run_id(args["name"], moment(args["start"]))


def written_files(root):
    found = {}
    for folder, _, names in os.walk(root):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                found = {**found, relative(path, root): handle.read()}
    return found


def run_case(writer, case, folder):
    root = os.path.join(folder, "root")
    home = os.path.join(folder, "home")
    os.makedirs(root)
    os.makedirs(home)
    environ = {name: substituted(value, root, home) for name, value in case["environ"].items()}
    returns = [reported(call_result(writer, call, environ, root, home), root) for call in case["calls"]]
    return {"files": written_files(root), "returns": returns}


def expected_outcome(written):
    files = {path: text.encode("utf-8") for path, text in written["files"].items()}
    return {"files": files, "returns": written["returns"]}


class WriterConformance(unittest.TestCase):
    def test_writer_matches_fixtures(self):
        from lighthouse_tool import metrics_writer

        folder = scratch.temporary_folder(self, "lh-metrics-")
        store = os.path.join(folder, "store")
        home = os.path.join(folder, "home")
        os.makedirs(store)
        os.makedirs(home)
        expected = fixture("expected.json")
        cases = fixture("cases.json")
        with mock.patch.dict(os.environ, {"PLUGIN_METRICS_DIR": store, "HOME": home}):
            outcome = {case["name"]: run_case(metrics_writer, case, os.path.join(folder, case["name"])) for case in cases}
        self.assertEqual(sorted(outcome), sorted(expected))
        for name, written in expected.items():
            with self.subTest(case=name):
                self.assertEqual(outcome[name], expected_outcome(written))
        self.assertEqual(os.listdir(store), [])

    def test_line_schema_names_the_envelope(self):
        with open(LINE_SCHEMA, encoding="utf-8") as handle:
            schema = json.load(handle)
        self.assertEqual(schema["required"], ENVELOPE)


class ScratchEnvironment(unittest.TestCase):
    def test_scratch_withholds_metrics_variables(self):
        planted = {"PLUGIN_METRICS_DIR": "/somewhere", "PLUGIN_METRICS_PARENT": "pipeline/feat-a.20261001T100000Z"}
        with mock.patch.dict(os.environ, planted):
            environment = scratch.base_environment()
        self.assertEqual(sorted(name for name in planted if name in environment), [])


if __name__ == "__main__":
    unittest.main()
