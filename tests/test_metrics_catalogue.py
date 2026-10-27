import json
import os
import re
import unittest

from tests import scratch

CATALOGUE = os.path.join(scratch.ROOT, "lighthouse_tool", "catalogue.json")
SCHEMA = os.path.join(scratch.ROOT, "metrics", "schema", "catalogue.schema.json")
DESCRIPTION_KEYS = ("type", "description", "measured_from", "unit", "includes", "excludes", "reading", "readers", "question")
UNITS = ("seconds", "usd", "tokens", "count", "ratio", "id", "text", "timestamp", "none")
TOKEN_KINDS = ["input", "cache_write_5m", "cache_write_1h", "cache_read", "output"]
JUDGING = re.compile(r"\b(good|bad|should|better|worse|healthy|unhealthy)\b", re.IGNORECASE)
OBJECTIVES = ["verdict", "suite", "new-behaviour", "neighbours", "cost"]


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def nested_entries(label, entry):
    inner = [
        found
        for name, child in entry.get("fields", {}).items()
        for found in nested_entries("{}.{}".format(label, name), child)
    ]
    items = nested_entries(label + "[]", entry["items"]) if "items" in entry else []
    return [(label, entry)] + inner + items


def every_field(catalogue):
    event_fields = [
        found
        for event, described in catalogue["events"].items()
        for name, entry in described["fields"].items()
        for found in nested_entries("{}.{}".format(event, name), entry)
    ]
    summary_fields = [
        found for name, entry in catalogue["summary"]["fields"].items() for found in nested_entries("summary." + name, entry)
    ]
    return event_fields + summary_fields


def field_name(label):
    return label.rsplit(".", 1)[-1]


def is_list_item(label):
    return label.endswith("[]")


class CatalogueTest(unittest.TestCase):
    def test_catalogue_meets_the_schema(self):
        catalogue = read_json(CATALOGUE)
        schema = read_json(SCHEMA)
        for key in schema["required"]:
            self.assertIn(key, catalogue)
        self.assertEqual(catalogue["format"], 1)
        self.assertEqual(catalogue["plugin"], "lighthouse")
        self.assertIn("FEATURE branch", catalogue["purpose"])
        self.assertIn("before it merges into its core branch", catalogue["purpose"])
        self.assertEqual(sorted(catalogue["events"]), ["run.end", "run.start"])
        for event in catalogue["events"].values():
            for key in ("description", "writer", "readers", "questions", "fields"):
                self.assertIn(key, event)
        for key in ("description", "fields"):
            self.assertIn(key, catalogue["summary"])
        for query in catalogue["queries"]:
            self.assertEqual(sorted(query), ["name", "question", "sql"])
        field_required = schema["$defs"]["field"]["required"]
        for label, entry in every_field(catalogue):
            with self.subTest(field=label):
                for key in field_required:
                    self.assertIn(key, entry)
                self.assertIn(entry["type"], schema["$defs"]["field"]["properties"]["type"]["enum"])

    def test_objectives_name_described_fields(self):
        catalogue = read_json(CATALOGUE)
        objectives = catalogue["objectives"]
        self.assertEqual([objective["id"] for objective in objectives], OBJECTIVES)
        described = {"summary." + name for name in catalogue["summary"]["fields"]} | {
            "{}.{}".format(event, name)
            for event, entry in catalogue["events"].items()
            for name in entry["fields"]
        }
        for objective in objectives:
            with self.subTest(objective=objective["id"]):
                self.assertTrue(objective["text"].strip())
                self.assertTrue(objective["measured_by"])
                for measure in objective["measured_by"]:
                    self.assertIn(measure, described)

    def test_every_field_is_described(self):
        catalogue = read_json(CATALOGUE)
        fields = every_field(catalogue)
        self.assertTrue(fields)
        for label, entry in fields:
            with self.subTest(field=label):
                for key in DESCRIPTION_KEYS:
                    self.assertIn(key, entry)
                self.assertIn(entry["unit"], UNITS)
                self.assertTrue(entry["readers"])
                if entry["type"] == "enum":
                    self.assertTrue(entry["values"])

    def test_shared_measures_have_their_units(self):
        catalogue = read_json(CATALOGUE)
        named = [(label, entry) for label, entry in every_field(catalogue) if not is_list_item(label)]
        usd = [entry for label, entry in named if field_name(label) == "usd"]
        seconds = [entry for label, entry in named if field_name(label).endswith("_seconds")]
        tokens = [entry for label, entry in named if field_name(label) == "tokens"]
        self.assertTrue(usd and seconds and tokens)
        for entry in usd:
            self.assertEqual(entry["unit"], "usd")
        for entry in seconds:
            self.assertEqual(entry["unit"], "seconds")
        for entry in tokens:
            self.assertEqual(entry["type"], "object")
            self.assertEqual(list(entry["fields"]), TOKEN_KINDS)
            for kind in entry["fields"].values():
                self.assertEqual((kind["type"], kind["unit"]), ("integer", "tokens"))

    def test_readings_never_judge(self):
        catalogue = read_json(CATALOGUE)
        for label, entry in every_field(catalogue):
            with self.subTest(field=label):
                self.assertIsNone(JUDGING.search(entry["reading"]), entry["reading"])


if __name__ == "__main__":
    unittest.main()
