import json
import os
import re
import unittest

from tests import scratch


def read_json(*parts):
    with open(os.path.join(scratch.ROOT, *parts), encoding="utf-8") as handle:
        return json.load(handle)


def read_text(*parts):
    with open(os.path.join(scratch.ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class LayoutTest(unittest.TestCase):
    def test_manifests_and_version(self):
        plugin = read_json(".claude-plugin", "plugin.json")
        marketplace = read_json(".claude-plugin", "marketplace.json")
        self.assertEqual(plugin["name"], "lighthouse")
        self.assertEqual(marketplace["name"], "lighthouse")
        self.assertEqual([entry["name"] for entry in marketplace["plugins"]], ["lighthouse"])
        self.assertTrue(os.access(scratch.LIGHTHOUSE, os.X_OK))

        code, stdout, stderr = scratch.run_lighthouse(["version"], scratch.environment(scratch.make_home(self)))

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout), {"version": plugin["version"]})

    def test_ci_runs_the_suite_and_validates(self):
        workflow = read_text(".github", "workflows", "ci.yml")
        triggers = workflow.split("\non:", 1)[1].split("\npermissions:", 1)[0]
        self.assertRegex(triggers, r"(?m)^  push:")
        self.assertRegex(triggers, r"(?m)^  pull_request:")
        versions = re.search(r"python:\s*\[([^\]]*)\]", workflow).group(1)
        self.assertEqual([version.strip(" '\"") for version in versions.split(",")], ["3.9", "3.14"])
        self.assertIn("python-version: ${{ matrix.python }}", workflow)
        self.assertRegex(workflow, r"(?m)run: python -m unittest discover tests$")
        self.assertRegex(workflow, r"(?m)run: npx .*claude-code@\S+ plugin validate --strict \.$")
        self.assertRegex(workflow, r"(?m)plugin validate --strict \.claude-plugin/plugin\.json$")


    def test_version_is_0_2_0(self):
        plugin = read_json(".claude-plugin", "plugin.json")
        self.assertEqual(plugin["version"], "0.4.0")

        code, stdout, stderr = scratch.run_lighthouse(["version"], scratch.environment(scratch.make_home(self)))

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout), {"version": "0.4.0"})

if __name__ == "__main__":
    unittest.main()
