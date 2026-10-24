import json
import os
import unittest

from tests import e2e_harness

BASELINE = os.path.join(e2e_harness.ROOT, "tests", "held_out_baseline.json")
SEED_TOKENS = 200000


def read_baseline():
    with open(BASELINE, encoding="utf-8") as handle:
        return json.load(handle)


def outcome(record):
    return "{} {} run {}: verdict {}, met {}, {:.1f} minutes, ${:.2f}".format(
        record["fixture"],
        record["variant"],
        record["run"],
        e2e_harness.verdict_of(record),
        record["met"],
        record["minutes"],
        record["dollars"],
    )


def totals(measured, baseline):
    return [
        "minutes {:.1f} against the baseline's {:.1f}".format(measured["minutes"], baseline["minutes"]),
        "dollars {:.2f} against the baseline's {:.2f}".format(measured["dollars"], baseline["dollars"]),
        "broken_green {} against the baseline's {}".format(measured["broken_green"], baseline["broken_green"]),
        "met {} against the baseline's {}".format(json.dumps(measured["met"]), json.dumps(baseline["met"])),
        "seed {}".format(json.dumps(measured["seed"])),
    ]


@unittest.skipUnless(e2e_harness.E2E, "end-to-end tests run only when LIGHTHOUSE_E2E=1")
class HeldOutEndToEndTest(unittest.TestCase):
    def test_held_out_fixtures(self):
        self.assertTrue(os.path.isfile(BASELINE), "measure main first with python3 -m tests.measure_held_out")
        baseline = read_baseline()
        measured = e2e_harness.measured_pass(self, e2e_harness.held_out_cases())
        for record in measured["cases"]:
            print(outcome(record))
        for line in totals(measured, baseline):
            print(line)
        for record in measured["cases"]:
            with self.subTest(fixture=record["fixture"], variant=record["variant"], run=record["run"]):
                self.assertIsNotNone(record["line"], record["transcript"])
                self.assertEqual(record["after"], record["before"], record["transcript"])
        self.assertGreaterEqual(sum(measured["seed"]["tokens"].values()), SEED_TOKENS, json.dumps(measured["seed"]))
        self.assertEqual(e2e_harness.bar_problems(measured, baseline), [])


if __name__ == "__main__":
    unittest.main()
