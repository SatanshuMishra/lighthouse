import json
import os
import unittest

from lighthouse_tool import child_reply, verdict
from lighthouse_tool.child_reply import Fault, Reading
from tests import scratch

H13_FILE = os.path.join(scratch.ROOT, "tests", "contracts", "h13-lighthouse-verdict-line.schema.json")
PULL_REQUEST = "https://github.com/o/r/pull/7"
BLOCKED = {
    "verdict": "blocked",
    "failures": [],
    "unproven": [],
    "flaky": [],
    "tokens": 0,
    "minutes": 0,
    "pr": None,
    "reason": "the profile is broken",
}
GREEN = {
    "verdict": "green",
    "failures": [],
    "unproven": [],
    "flaky": [],
    "tokens": 1200,
    "minutes": 3,
    "dollars": 1.25,
    "pr": None,
}
FAILURES_REPLY = {
    "verdict": "failures",
    "failures": ["export writes a csv"],
    "unproven": [],
    "flaky": [],
    "tokens": 900,
    "minutes": 4,
    "dollars": 1.5,
    "pr": PULL_REQUEST,
}
FINDINGS = {
    "version": 1,
    "suite": {
        "result": "passed",
        "reason": None,
        "failures": [],
        "pre_existing": [],
        "flaky": [],
        "core": None,
        "feature": None,
    },
    "build": {"result": "ok", "reason": None},
    "paths": [
        {
            "name": "one",
            "kind": "new",
            "surface": "cli",
            "expected": "works",
            "evidence": ["evidence/one.log"],
            "status": "passed",
            "retry": None,
            "core": None,
            "trials": None,
            "check": {"kind": "direct", "why": "it answers"},
        }
    ],
    "spend": {"tokens": 10, "minutes": 1, "dollars": None},
}
SKIPPED_FINDINGS = {**FINDINGS, "paths": [{**FINDINGS["paths"][0], "status": "skipped"}]}
FAULTS = (
    Fault("findings.json", "h14-lighthouse-findings.schema.json", ('#/paths/0/status enum: "skipped" is not one of the allowed values',)),
    Fault("the reply's structured_output", "the reply schema built from h13-lighthouse-verdict-line.schema.json", ("#/verdict_line oneOf: first", "#/verdict_line/note additionalProperties: second")),
)


def read_h13():
    with open(H13_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def envelope(line):
    return {"session_id": "s1", "structured_output": {"verdict_line": line}}


def write(folder, name, value):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
        handle.write(value if isinstance(value, str) else json.dumps(value) + "\n")


class ReplySchemaTest(unittest.TestCase):
    def test_the_reply_schema_is_an_object_whose_required_verdict_line_is_h13s_verdict_or_blocked_form(self):
        schema = child_reply.reply_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["required"], ["verdict_line"])
        self.assertEqual(
            schema["properties"],
            {"verdict_line": {"oneOf": [{"$ref": "#/$defs/verdict"}, {"$ref": "#/$defs/blocked"}]}},
        )
        self.assertEqual(schema["$defs"], read_h13()["$defs"])
        for key in ("$schema", "$id", "oneOf"):
            self.assertNotIn(key, schema)

    def test_the_schema_argument_is_the_schema_as_json(self):
        schema = child_reply.reply_schema()
        self.assertEqual(json.loads(child_reply.schema_argument(schema)), schema)


class EnvelopeTest(unittest.TestCase):
    def test_only_a_json_object_with_a_session_id_is_an_envelope(self):
        rows = [
            (b"Error: not json at all", None),
            (b"[1, 2]", None),
            (b'{"result": "done"}', None),
            (b'{"session_id": 3}', None),
            (b'{"session_id": "--rf"}', None),
            (b'{"session_id": "s1", "result": "done"}', {"session_id": "s1", "result": "done"}),
        ]
        for output, expected in rows:
            with self.subTest(output=output):
                self.assertEqual(child_reply.envelope_of(output), expected)


class ReadReplyTest(unittest.TestCase):
    def setUp(self):
        self.results = scratch.temporary_folder(self, "lh-reply-")
        self.schema = child_reply.reply_schema()

    def read(self, given):
        return child_reply.read_reply(given, self.results, self.schema)

    def test_a_blocked_reply_is_read_unchanged(self):
        self.assertEqual(self.read(envelope(BLOCKED)), Reading(BLOCKED, ()))

    def test_the_result_text_is_never_read(self):
        reading = self.read({"session_id": "s1", "result": json.dumps(BLOCKED)})
        self.assertIsNone(reading.line)
        self.assertEqual(
            reading.faults,
            (
                Fault(
                    "the reply",
                    "the reply schema built from h13-lighthouse-verdict-line.schema.json",
                    ("# required: the reply carries no structured_output",),
                ),
            ),
        )

    def test_a_reply_with_a_key_h13_does_not_define_is_a_fault_naming_it(self):
        reading = self.read(envelope({**BLOCKED, "note": "x"}))
        self.assertIsNone(reading.line)
        self.assertEqual(len(reading.faults), 1)
        fault = reading.faults[0]
        self.assertEqual(fault.subject, "the reply's structured_output")
        self.assertIn("h13-lighthouse-verdict-line", fault.schema)
        self.assertIn('#/verdict_line/note additionalProperties: property "note" is not allowed', " ".join(fault.errors))

    def test_structured_output_that_is_not_an_object_is_a_fault(self):
        reading = self.read({"session_id": "s1", "structured_output": "green"})
        self.assertIsNone(reading.line)
        self.assertEqual(reading.faults[0].errors[0], '# type: "green" is not of type object')

    def test_a_verdict_reply_prints_verdict_json_with_the_replys_pr(self):
        write(self.results, "verdict.json", GREEN)
        write(self.results, "findings.json", FINDINGS)
        self.assertEqual(self.read(envelope(FAILURES_REPLY)), Reading({**GREEN, "pr": PULL_REQUEST}, ()))

    def test_a_verdict_reply_without_its_files_names_each_file(self):
        reading = self.read(envelope(GREEN))
        self.assertIsNone(reading.line)
        self.assertEqual(
            reading.faults,
            (
                Fault("findings.json", "h14-lighthouse-findings.schema.json", ("# missing: the child session left no findings.json",)),
                Fault(
                    "verdict.json",
                    "h13-lighthouse-verdict-line.schema.json#/$defs/verdict",
                    ("# missing: the child session left no verdict.json",),
                ),
            ),
        )

    def test_findings_breaking_h14_is_a_fault_naming_h14_and_the_error(self):
        write(self.results, "verdict.json", GREEN)
        write(self.results, "findings.json", SKIPPED_FINDINGS)
        reading = self.read(envelope(GREEN))
        self.assertIsNone(reading.line)
        self.assertEqual(len(reading.faults), 1)
        self.assertEqual(reading.faults[0].subject, "findings.json")
        self.assertEqual(reading.faults[0].schema, "h14-lighthouse-findings.schema.json")
        self.assertTrue(reading.faults[0].errors[0].startswith("#/paths/0/status enum:"), reading.faults[0].errors)

    def test_verdict_json_that_is_not_json_or_not_a_verdict_form_is_a_fault(self):
        write(self.results, "findings.json", FINDINGS)
        rows = [
            ("not json\n", ("# type: verdict.json is not JSON",)),
            (json.dumps(BLOCKED) + "\n", None),
        ]
        for text, expected in rows:
            with self.subTest(text=text):
                write(self.results, "verdict.json", text)
                reading = self.read(envelope(GREEN))
                self.assertIsNone(reading.line)
                self.assertEqual([fault.subject for fault in reading.faults], ["verdict.json"])
                if expected is not None:
                    self.assertEqual(reading.faults[0].errors, expected)


class WordingTest(unittest.TestCase):
    def test_the_re_ask_prompt_names_every_file_schema_and_error_on_one_line(self):
        prompt = child_reply.re_ask_prompt(FAULTS)
        for expected in (
            "findings.json fails h14-lighthouse-findings.schema.json",
            '#/paths/0/status enum: "skipped" is not one of the allowed values',
            "the reply's structured_output fails the reply schema built from h13-lighthouse-verdict-line.schema.json",
            "#/verdict_line oneOf: first; #/verdict_line/note additionalProperties: second",
            "lighthouse findings",
            "verdict_line",
        ):
            self.assertIn(expected, prompt)
        self.assertNotIn("\n", prompt)

    def test_the_blocked_reason_names_every_schema_and_error_and_makes_an_h13_blocked_line(self):
        reason = child_reply.blocked_reason(FAULTS)
        self.assertIn("h14-lighthouse-findings.schema.json", reason)
        self.assertIn("h13-lighthouse-verdict-line.schema.json", reason)
        self.assertIn("#/verdict_line/note additionalProperties: second", reason)
        code, line, _ = verdict.blocked_line(reason)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(line)["reason"], reason)

    def test_the_no_json_reason_names_the_kept_file(self):
        self.assertEqual(
            child_reply.no_json_reason("/r/child.out"),
            "the child session printed no JSON result with a session_id; its output is kept in /r/child.out",
        )


if __name__ == "__main__":
    unittest.main()
