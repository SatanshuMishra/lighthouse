import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from milepost import trips
from milepost.cli import main


def run(argv):
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = main(argv)
    return code, output.getvalue(), errors.getvalue()


class DropTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "trips.json")
        patcher = mock.patch.dict(os.environ, {"MILEPOST_DATA": self.path})
        patcher.start()
        self.addCleanup(patcher.stop)
        run(["log", "2026-03-02", "Lyon", "42"])
        run(["log", "2026-03-05", "Dijon", "18.5"])
        run(["log", "2026-03-09", "Annecy", "63"])

    def places(self):
        return [entry["place"] for entry in trips.load(self.path)]

    def test_drop_removes_the_numbered_trip(self):
        code, _, _ = run(["drop", "2"])

        self.assertEqual(code, 0)
        self.assertEqual(self.places(), ["Lyon", "Annecy"])

    def test_drop_prints_the_trip_it_removed(self):
        _, output, _ = run(["drop", "2"])

        self.assertEqual(output, "Dropped 2. 2026-03-05  Dijon  18.5 km\n")

    def test_drop_keeps_the_total_in_step(self):
        run(["drop", "2"])

        _, output, _ = run(["total"])

        self.assertEqual(output, "Total: 105.0 km over 2 trips\n")

    def test_drop_refuses_a_number_no_trip_has(self):
        code, _, errors = run(["drop", "4"])

        self.assertEqual(code, 1)
        self.assertIn("no trip is numbered 4", errors)
        self.assertEqual(self.places(), ["Lyon", "Dijon", "Annecy"])


if __name__ == "__main__":
    unittest.main()
