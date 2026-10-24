import datetime
import json
import os
import unittest

from tests import scratch


def mark(test, results, *arguments):
    env = scratch.environment(scratch.make_home(test))
    return scratch.run_lighthouse(["mark", "--results", results, *arguments], env)


class MarkTest(unittest.TestCase):
    def test_mark_appends_a_timed_line(self):
        results = scratch.temporary_folder(self, "lh-results-")
        code, stdout, stderr = mark(self, results, "--step", "drive", "--build", "feature", "--path", "sign in", "start")
        self.assertEqual(code, 0, stderr)
        with open(os.path.join(results, "marks.jsonl"), encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle.read().splitlines()]
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line["step"], "drive")
        self.assertEqual(line["build"], "feature")
        self.assertEqual(line["path"], "sign in")
        self.assertEqual(line["edge"], "start")
        moment = datetime.datetime.fromisoformat(line["time"].replace("Z", "+00:00"))
        self.assertEqual(moment.utcoffset(), datetime.timedelta(0))
        self.assertEqual(json.loads(stdout.strip().splitlines()[-1]), line)

    def test_mark_refuses_an_unknown_build_or_edge(self):
        results = scratch.temporary_folder(self, "lh-results-")
        for arguments in (["--step", "drive", "--build", "staging", "start"], ["--step", "drive", "middle"]):
            code, stdout, _ = mark(self, results, *arguments)
            self.assertEqual(code, 2, arguments)
            self.assertIn("error", json.loads(stdout))
        self.assertFalse(os.path.exists(os.path.join(results, "marks.jsonl")))


if __name__ == "__main__":
    unittest.main()
