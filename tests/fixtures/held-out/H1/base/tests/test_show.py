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

    def test_show_numbers_every_trip(self):
        run(["log", "2026-03-02", "Lyon", "42"])
        run(["log", "2026-03-05", "Dijon", "18.5"])

        code, output = run(["show"])

        self.assertEqual(code, 0)
        self.assertEqual(output, "1. 2026-03-02  Lyon  42.0 km\n2. 2026-03-05  Dijon  18.5 km\n")

    def test_show_says_so_when_nothing_is_logged(self):
        code, output = run(["show"])

        self.assertEqual(code, 0)
        self.assertEqual(output, "No trips logged.\n")


if __name__ == "__main__":
    unittest.main()
