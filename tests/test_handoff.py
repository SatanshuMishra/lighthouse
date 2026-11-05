import unittest

from lighthouse_tool import handoff
from lighthouse_tool.repo import Refusal

FEATURE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
K1 = "k1-acceptance.schema.json"
K3 = "k3-check-result.schema.json"


def k1_line(**changes):
    line = {
        "id": "C1.1",
        "kind": "exact",
        "surface": {"family": "cli", "target": "bin/lighthouse"},
        "command": "true",
        "pass": "exit 0",
    }
    return {**line, **changes}


def k3_result(**changes):
    result = {
        "check_id": "C1.1",
        "commit": FEATURE_COMMIT,
        "surface": {"family": "cli", "target": "bin/lighthouse"},
        "status": "pass",
        "evidence": ["evidence/checks/C1.1-1.log"],
        "seconds": 0.5,
        "runner": "lighthouse execute",
    }
    return {**result, **changes}


class SchemaErrorsTest(unittest.TestCase):
    def test_a_value_that_meets_its_format_has_no_errors(self):
        self.assertEqual(handoff.schema_errors(K1, k1_line()), [])

    def test_every_error_of_a_value_is_returned(self):
        errors = handoff.schema_errors(K1, k1_line(id="X1", note="x"))
        self.assertEqual(
            errors,
            [
                '#/id pattern: "X1" does not match "^C[0-9]+\\\\.[0-9]+$"',
                '#/note additionalProperties: property "note" is not allowed',
            ],
        )

    def test_a_schema_is_named_with_or_without_its_suffix(self):
        self.assertEqual(handoff.schema_errors("k1-acceptance", k1_line(kind="loose")), handoff.schema_errors(K1, k1_line(kind="loose")))
        self.assertEqual(handoff.schema_file("k1-acceptance"), K1)

    def test_a_reference_to_a_sibling_schema_is_followed(self):
        errors = handoff.schema_errors(K3, k3_result(surface={"family": "radio", "target": "x"}))
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("#/surface/family enum:"), errors)

    def test_an_unknown_schema_is_refused_by_name(self):
        with self.assertRaises(Refusal) as raised:
            handoff.schema_errors("h99-nothing.schema.json", {})
        self.assertIn("h99-nothing.schema.json", str(raised.exception))


class CheckBeforeWritingTest(unittest.TestCase):
    def test_a_passing_value_is_returned_unchanged(self):
        result = k3_result()
        self.assertEqual(handoff.check_before_writing("checks.jsonl line for C1.1", K3, result), result)

    def test_a_failing_value_is_refused_naming_the_target_the_schema_and_every_error(self):
        result = k3_result(status="maybe", seconds=-1)
        with self.assertRaises(handoff.FormatRefusal) as raised:
            handoff.check_before_writing("checks.jsonl line for C1.1", K3, result)
        refusal = raised.exception
        self.assertIsInstance(refusal, Refusal)
        self.assertEqual(refusal.schema, K3)
        self.assertEqual(len(refusal.errors), 2, refusal.errors)
        self.assertEqual(
            str(refusal),
            "refusing to write checks.jsonl line for C1.1: it fails k3-check-result.schema.json: " + "; ".join(refusal.errors),
        )
        self.assertIn("#/status enum", str(refusal))
        self.assertIn("#/seconds minimum", str(refusal))


class ReadThroughTest(unittest.TestCase):
    def test_a_passing_value_is_returned_unchanged(self):
        line = k1_line()
        self.assertEqual(handoff.read_through("interphase", "record r.json", K1, line), line)

    def test_a_failing_value_is_refused_naming_the_producer_the_source_the_schema_and_every_error(self):
        with self.assertRaises(handoff.FormatRefusal) as raised:
            handoff.read_through("interphase", "acceptance line C1.1 of record r.json", K1, k1_line(kind="judged"))
        refusal = raised.exception
        self.assertEqual(
            str(refusal),
            "acceptance line C1.1 of record r.json from interphase fails k1-acceptance.schema.json: "
            + "; ".join(refusal.errors),
        )
        self.assertEqual(
            refusal.errors,
            ('# required: lacks required property "rubric"', '# required: lacks required property "trials"'),
        )


if __name__ == "__main__":
    unittest.main()
