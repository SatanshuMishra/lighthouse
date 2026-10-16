import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from milepost import trips
from milepost.cli import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(argv):
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = main(argv)
    return code, output.getvalue(), errors.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "trips.json")
        patcher = mock.patch.dict(os.environ, {"MILEPOST_DATA": self.path})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_log_records_the_trip(self):
        code, output, _ = run(["log", "2026-03-02", "Lyon", "42"])

        self.assertEqual(code, 0)
        self.assertEqual(output, "Logged 2026-03-02 Lyon 42.0 km\n")
        self.assertEqual(trips.load(self.path), [{"date": "2026-03-02", "place": "Lyon", "km": 42.0}])

    def test_log_refuses_a_day_that_is_not_a_date(self):
        code, _, errors = run(["log", "March 2", "Lyon", "42"])

        self.assertEqual(code, 2)
        self.assertIn("YYYY-MM-DD", errors)
        self.assertEqual(trips.load(self.path), [])

    def test_total_adds_up_every_trip(self):
        run(["log", "2026-03-02", "Lyon", "42"])
        run(["log", "2026-03-05", "Dijon", "18.5"])

        code, output, _ = run(["total"])

        self.assertEqual(code, 0)
        self.assertEqual(output, "Total: 60.5 km over 2 trips\n")

    def test_runs_as_a_module(self):
        completed = subprocess.run(
            [sys.executable, "-m", "milepost", "total"],
            cwd=ROOT,
            env={**os.environ, "MILEPOST_DATA": self.path},
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Total: 0.0 km over 0 trips\n")


if __name__ == "__main__":
    unittest.main()
