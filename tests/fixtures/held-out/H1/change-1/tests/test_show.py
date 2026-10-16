import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from milepost.cli import main


def run(argv):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(argv)
    return code, output.getvalue()


class ShowTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.dict(os.environ, {"MILEPOST_DATA": os.path.join(folder.name, "trips.json")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_show_numbers_the_newest_trip_first(self):
        run(["log", "2026-03-02", "Lyon", "42"])
        run(["log", "2026-03-05", "Dijon", "18.5"])

        code, output = run(["show"])

        self.assertEqual(code, 0)
        self.assertEqual(output, "1. 2026-03-05  Dijon  18.5 km\n2. 2026-03-02  Lyon  42.0 km\n")

    def test_show_orders_by_the_day_of_the_trip(self):
        run(["log", "2026-03-05", "Dijon", "18.5"])
        run(["log", "2026-03-09", "Annecy", "63"])
        run(["log", "2026-03-02", "Lyon", "42"])

        _, output = run(["show"])

        self.assertEqual(
            output,
            "1. 2026-03-09  Annecy  63.0 km\n2. 2026-03-05  Dijon  18.5 km\n3. 2026-03-02  Lyon  42.0 km\n",
        )

    def test_show_says_so_when_nothing_is_logged(self):
        code, output = run(["show"])

        self.assertEqual(code, 0)
        self.assertEqual(output, "No trips logged.\n")


if __name__ == "__main__":
    unittest.main()
