import json
import os
import unittest

from lighthouse_tool import handoff, record_lines
from lighthouse_tool.repo import Refusal
from tests import scratch

SOURCE = "/records/x.record.json"


def k1_line(identifier="C1.1", **changes):
    line = {
        "id": identifier,
        "kind": "exact",
        "surface": {"family": "cli", "target": "bin/lighthouse execute"},
        "command": "true",
        "pass": "exit 0",
    }
    return {**line, **changes}


def write_text(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class AcceptanceLinesTest(unittest.TestCase):
    def refused(self, record):
        with self.assertRaises(Refusal) as raised:
            record_lines.acceptance_lines(record, SOURCE)
        return str(raised.exception)

    def test_every_line_of_every_criterion_is_read_in_order(self):
        record = {
            "criteria": [
                {"number": "1.1", "acceptance": [k1_line("C1.1"), k1_line("C1.2")]},
                {"number": "1.2"},
                {"number": "1.3", "acceptance": [k1_line("C3.1")]},
            ]
        }
        lines = record_lines.acceptance_lines(record, SOURCE)
        self.assertEqual([line["id"] for line in lines], ["C1.1", "C1.2", "C3.1"])
        self.assertEqual(lines[0], k1_line("C1.1"))

    def test_a_record_without_criteria_is_refused(self):
        self.assertEqual(self.refused({}), "record /records/x.record.json: #/criteria must be a list of criteria")

    def test_criteria_that_is_not_a_list_is_refused(self):
        self.assertEqual(
            self.refused({"criteria": {"number": "1.1"}}),
            "record /records/x.record.json: #/criteria must be a list of criteria",
        )

    def test_a_criterion_that_is_not_an_object_is_refused_by_its_index(self):
        record = {"criteria": [{"acceptance": [k1_line()]}, "loose"]}
        self.assertEqual(self.refused(record), "record /records/x.record.json: #/criteria/1 is not an object")

    def test_an_acceptance_that_is_not_a_list_is_refused(self):
        record = {"criteria": [{"acceptance": k1_line()}]}
        self.assertEqual(
            self.refused(record),
            "record /records/x.record.json: #/criteria/0/acceptance must be a list of acceptance lines",
        )

    def test_a_line_that_fails_k1_is_refused_naming_interphase_the_schema_and_every_error(self):
        record = {"criteria": [{"acceptance": [k1_line(), k1_line("C1.2", kind="loose", note="x")]}]}
        with self.assertRaises(handoff.FormatRefusal) as raised:
            record_lines.acceptance_lines(record, SOURCE)
        self.assertEqual(
            str(raised.exception),
            "acceptance line C1.2 at #/criteria/0/acceptance/1 of record /records/x.record.json from interphase "
            'fails k1-acceptance.schema.json: #/kind enum: "loose" is not one of "exact", "judged"; '
            '#/note additionalProperties: property "note" is not allowed',
        )

    def test_a_line_that_is_not_an_object_is_refused_by_its_position(self):
        record = {"criteria": [{"acceptance": ["C1.1"]}]}
        message = self.refused(record)
        self.assertTrue(
            message.startswith(
                "acceptance line #/criteria/0/acceptance/0 of record /records/x.record.json from interphase "
                "fails k1-acceptance.schema.json: # type:"
            ),
            message,
        )

    def test_a_repeated_id_is_refused_at_its_second_place(self):
        record = {"criteria": [{"acceptance": [k1_line("C2.1")]}, {"acceptance": [k1_line("C2.1", command="false")]}]}
        self.assertEqual(
            self.refused(record),
            "acceptance line C2.1 at #/criteria/1/acceptance/0 of record /records/x.record.json repeats the id C2.1",
        )

    def test_the_record_is_left_unchanged(self):
        record = {"criteria": [{"acceptance": [k1_line()]}]}
        before = json.dumps(record, sort_keys=True)
        lines = record_lines.acceptance_lines(record, SOURCE)
        self.assertEqual(json.dumps(record, sort_keys=True), before)
        self.assertIsNot(lines[0], record["criteria"][0]["acceptance"][0])


class ReadRecordTest(unittest.TestCase):
    def test_lines_are_read_from_the_record_file(self):
        folder = scratch.temporary_folder(self, "lh-record-")
        path = write_text(folder, "record.json", json.dumps({"criteria": [{"acceptance": [k1_line("C4.2")]}]}))
        self.assertEqual(record_lines.lines_at(path), [k1_line("C4.2")])

    def test_a_missing_record_is_refused_by_path(self):
        folder = scratch.temporary_folder(self, "lh-record-")
        path = os.path.join(folder, "absent.json")
        with self.assertRaises(Refusal) as raised:
            record_lines.lines_at(path)
        self.assertIn("record {} cannot be read".format(path), str(raised.exception))

    def test_a_record_that_is_not_json_is_refused_by_path(self):
        folder = scratch.temporary_folder(self, "lh-record-")
        path = write_text(folder, "record.json", "{criteria")
        with self.assertRaises(Refusal) as raised:
            record_lines.lines_at(path)
        self.assertIn("record {} is not JSON".format(path), str(raised.exception))

    def test_a_record_that_is_not_an_object_is_refused_by_path(self):
        folder = scratch.temporary_folder(self, "lh-record-")
        path = write_text(folder, "record.json", "[]")
        with self.assertRaises(Refusal) as raised:
            record_lines.lines_at(path)
        self.assertEqual(str(raised.exception), "record {} is not a JSON object".format(path))


if __name__ == "__main__":
    unittest.main()
