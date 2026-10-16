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
        return sorted(entry["place"] for entry in trips.load(self.path))

    def shown_line(self, place):
        _, output, _ = run(["show"])
        return next(line for line in output.splitlines() if "  {}  ".format(place) in line)

    def test_drop_removes_the_trip_show_numbers(self):
        for place in ("Lyon", "Dijon", "Annecy"):
            with self.subTest(place=place):
                line = self.shown_line(place)
                code, output, _ = run(["drop", line.split(".")[0]])

                self.assertEqual(code, 0)
                self.assertEqual(output, "Dropped {}\n".format(line))
                self.assertNotIn(place, self.places())

    def test_drop_keeps_the_total_in_step(self):
        run(["drop", self.shown_line("Dijon").split(".")[0]])

        _, output, _ = run(["total"])

        self.assertEqual(output, "Total: 105.0 km over 2 trips\n")

    def test_drop_refuses_a_number_no_trip_has(self):
        code, _, errors = run(["drop", "4"])

        self.assertEqual(code, 1)
        self.assertIn("no trip is numbered 4", errors)
        self.assertEqual(self.places(), ["Annecy", "Dijon", "Lyon"])


if __name__ == "__main__":
    unittest.main()
