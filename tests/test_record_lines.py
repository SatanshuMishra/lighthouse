import json
import os
import unittest

from lighthouse_tool import handoff, record_lines
from lighthouse_tool.repo import Refusal
from tests import scratch

SOURCE = "/records/x.record.json"
H11_REFUSAL = "record /records/x.record.json from interphase fails h11-interphase-record.schema.json: "


def k1_line(identifier="C1.1", **changes):
    line = {
        "id": identifier,
        "kind": "exact",
        "surface": {"family": "cli", "target": "bin/lighthouse execute"},
        "command": "true",
        "pass": "exit 0",
    }
    return {**line, **changes}


def record_of(*criteria):
    return scratch.h11_record(list(criteria))


def criterion(number, lines=None):
    return scratch.h11_criterion(number, lines)


def write_text(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class AcceptanceLinesTest(unittest.TestCase):
    def refused(self, record):
        with self.assertRaises(Refusal) as raised:
            record_lines.acceptance_lines(record, SOURCE)
        return raised.exception

    def test_every_line_of_every_criterion_is_read_in_order(self):
        record = record_of(
            criterion("1.1", [k1_line("C1.1"), k1_line("C1.2")]),
            criterion("1.2"),
            criterion("1.3", [k1_line("C3.1")]),
        )
        lines = record_lines.acceptance_lines(record, SOURCE)
        self.assertEqual([line["id"] for line in lines], ["C1.1", "C1.2", "C3.1"])
        self.assertEqual(lines[0], k1_line("C1.1"))

    def test_a_criterion_without_acceptance_holds_no_line_and_is_not_refused(self):
        record = record_of(criterion("1.1"), criterion("1.2"))
        self.assertEqual(record_lines.acceptance_lines(record, SOURCE), [])

    def test_a_record_failing_h11_is_refused_naming_interphase_the_schema_and_every_error(self):
        record = {"criteria": [{"number": "1.1", "acceptance": [k1_line()]}]}
        refusal = self.refused(record)
        self.assertIsInstance(refusal, handoff.FormatRefusal)
        self.assertEqual(
            str(refusal),
            H11_REFUSAL
            + '# required: lacks required property "seams"; # required: lacks required property "steps"; '
            '# required: lacks required property "status"; #/criteria/0 required: lacks required property "title"; '
            '#/criteria/0 required: lacks required property "text"; '
            '#/criteria/0 required: lacks required property "seam"; '
            '#/criteria/0 required: lacks required property "tests"',
        )
        self.assertEqual(refusal.schema, "h11-interphase-record.schema.json")
        self.assertEqual(len(refusal.errors), 7)

    def test_a_record_failing_h11_only_is_refused_although_every_line_passes_k1(self):
        seamless = {key: value for key, value in criterion("1.1", [k1_line()]).items() if key != "seam"}
        self.assertEqual(
            str(self.refused(record_of(seamless))),
            H11_REFUSAL + '#/criteria/0 required: lacks required property "seam"',
        )

    def test_a_record_without_criteria_is_refused_by_h11(self):
        record = {key: value for key, value in record_of(criterion("1.1")).items() if key != "criteria"}
        self.assertEqual(str(self.refused(record)), H11_REFUSAL + '# required: lacks required property "criteria"')

    def test_criteria_that_is_not_a_list_is_refused_by_h11(self):
        record = {**record_of(criterion("1.1")), "criteria": {"number": "1.1"}}
        self.assertEqual(
            str(self.refused(record)), H11_REFUSAL + '#/criteria type: {"number": "1.1"} is not of type array'
        )

    def test_a_criterion_that_is_not_an_object_is_refused_by_h11_at_its_index(self):
        record = record_of(criterion("1.1", [k1_line()]), "loose")
        self.assertEqual(str(self.refused(record)), H11_REFUSAL + '#/criteria/1 type: "loose" is not of type object')

    def test_an_acceptance_that_is_not_a_list_is_refused_by_h11(self):
        record = record_of({**criterion("1.1"), "acceptance": k1_line()})
        message = str(self.refused(record))
        self.assertTrue(message.startswith(H11_REFUSAL + "#/criteria/0/acceptance type: "), message)
        self.assertTrue(message.endswith(" is not of type array"), message)

    def test_a_line_that_fails_k1_is_refused_through_h11_with_every_error(self):
        record = record_of(criterion("1.1", [k1_line(), k1_line("C1.2", kind="loose", note="x")]))
        self.assertEqual(
            str(self.refused(record)),
            H11_REFUSAL + '#/criteria/0/acceptance/1/kind enum: "loose" is not one of "exact", "judged"; '
            '#/criteria/0/acceptance/1/note additionalProperties: property "note" is not allowed',
        )

    def test_a_line_that_is_not_an_object_is_refused_by_h11_at_its_position(self):
        record = record_of(criterion("1.1", ["C1.1"]))
        self.assertEqual(
            str(self.refused(record)), H11_REFUSAL + '#/criteria/0/acceptance/0 type: "C1.1" is not of type object'
        )

    def test_a_repeated_id_is_refused_at_its_second_place(self):
        record = record_of(criterion("1.1", [k1_line("C2.1")]), criterion("1.2", [k1_line("C2.1", command="false")]))
        refusal = self.refused(record)
        self.assertNotIsInstance(refusal, handoff.FormatRefusal)
        self.assertEqual(
            str(refusal),
            "acceptance line C2.1 at #/criteria/1/acceptance/0 of record /records/x.record.json repeats the id C2.1",
        )

    def test_the_record_is_left_unchanged(self):
        record = record_of(criterion("1.1", [k1_line()]))
        before = json.dumps(record, sort_keys=True)
        lines = record_lines.acceptance_lines(record, SOURCE)
        self.assertEqual(json.dumps(record, sort_keys=True), before)
        self.assertIsNot(lines[0], record["criteria"][0]["acceptance"][0])


class ReadRecordTest(unittest.TestCase):
    def test_lines_are_read_from_the_record_file(self):
        folder = scratch.temporary_folder(self, "lh-record-")
        path = write_text(folder, "record.json", json.dumps(record_of(criterion("1.1", [k1_line("C4.2")]))))
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

    def test_a_record_that_is_not_an_object_is_refused_by_h11_naming_its_path(self):
        folder = scratch.temporary_folder(self, "lh-record-")
        path = write_text(folder, "record.json", "[]")
        with self.assertRaises(handoff.FormatRefusal) as raised:
            record_lines.lines_at(path)
        self.assertEqual(
            str(raised.exception),
            "record {} from interphase fails h11-interphase-record.schema.json: # type: [] is not of type object".format(
                path
            ),
        )


if __name__ == "__main__":
    unittest.main()
