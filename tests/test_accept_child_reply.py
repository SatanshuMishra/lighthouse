import json
import os
import unittest

from tests import accept_support as support

PULL_REQUEST = "https://github.com/o/r/pull/7"
RAW_OUTPUT = "Error: not json at all"


def shown(run):
    return run["stdout"] + run["stderr"]


class ChildReply(unittest.TestCase):
    def test_reply_is_read_from_structured_output(self):
        structured = support.blocked_line("structured reason")
        text = support.blocked_line("text reason")

        run = support.launched(self, [{"envelope": support.envelope(structured, result=json.dumps(text))}])

        self.assertEqual(run["code"], 0, shown(run))
        self.assertEqual(support.last_json(run["stdout"]), structured)
        self.assertEqual(len(run["calls"]), 1)
        argv = run["calls"][0]["argv"]
        self.assertEqual(support.value_after(argv, "--output-format"), "json", argv)
        schema = json.loads(support.value_after(argv, "--json-schema") or "null")
        self.assertIsInstance(schema, dict, argv)
        self.assertIn("verdict_line", schema.get("properties", {}))
        self.assertIn("verdict_line", schema.get("required", []))

    def test_a_reply_breaking_the_schema_is_re_asked_in_the_same_session(self):
        first = {**support.blocked_line("first"), "note": "x"}
        second = support.blocked_line("second")

        run = support.launched(self, [{"envelope": support.envelope(first)}, {"envelope": support.envelope(second)}])

        self.assertEqual(len(run["calls"]), 2, shown(run))
        argv = run["calls"][1]["argv"]
        self.assertEqual(support.value_after(argv, "--resume"), "s1", argv)
        self.assertIn("--json-schema", argv)
        self.assertIn("note", support.prompt_of(argv))
        self.assertEqual(support.last_json(run["stdout"]), second)

    def test_a_second_failure_blocks_naming_the_errors(self):
        broken = {"verdict": "maybe"}

        run = support.launched(self, [{"envelope": support.envelope(broken)}, {"envelope": support.envelope(broken)}])

        self.assertEqual(len(run["calls"]), 2, shown(run))
        self.assertEqual(run["code"], 0, shown(run))
        line = support.last_json(run["stdout"])
        self.assertEqual(support.referee_form_errors(support.H13, "blocked", line), ())
        self.assertIn(support.H13, line["reason"])

    def test_findings_breaking_h14_are_re_asked(self):
        green = dict(support.GREEN_LINE)
        opened = {**green, "pr": PULL_REQUEST}
        skipped = support.with_path(support.valid_findings(), status="skipped")
        valid = support.valid_findings()
        self.assertEqual(support.referee_errors(support.H14, valid), ())
        first = {
            "files": {
                "verdict.json": json.dumps(green) + "\n",
                "findings.json": json.dumps(skipped, indent=2) + "\n",
                "evidence/one.log": "one\n",
            },
            "envelope": support.envelope(green),
        }
        second = {"files": {"findings.json": json.dumps(valid, indent=2) + "\n"}, "envelope": support.envelope(opened)}

        run = support.launched(self, [first, second])

        self.assertEqual(len(run["calls"]), 2, shown(run))
        self.assertIn(support.H14, support.prompt_of(run["calls"][1]["argv"]))
        line = support.last_json(run["stdout"])
        self.assertEqual(line, opened)
        self.assertEqual(support.referee_errors(support.H13, line), ())

    def test_output_that_is_not_json_is_kept_and_blocks(self):
        run = support.launched(self, [{"raw": RAW_OUTPUT, "exit": 1}])

        self.assertEqual(len(run["calls"]), 1, shown(run))
        line = support.last_json(run["stdout"])
        self.assertEqual(line["verdict"], "blocked", shown(run))
        self.assertIn("child.out", line["reason"])
        self.assertEqual(support.read_bytes(os.path.join(run["results"], "child.out")), RAW_OUTPUT.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
