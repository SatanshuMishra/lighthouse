import contextlib
import io
import os
import unittest
from unittest import mock

from hearthctl.cli import main
from tests.fakes import FakeLink


def run(argv, link):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(argv, connect=lambda: link)
    return code, output.getvalue()


class CliTest(unittest.TestCase):
    def test_status_asks_for_the_temperature(self):
        link = FakeLink("19.5")

        code, output = run(["status"], link)

        self.assertEqual((code, output, link.sent), (0, "19.5\n", ["TEMP?"]))

    def test_set_sends_the_target(self):
        link = FakeLink()

        code, _ = run(["set", "21.5"], link)

        self.assertEqual((code, link.sent), (0, ["SET 21.5"]))

    def test_plan_needs_no_thermostat(self):
        link = FakeLink()

        code, output = run(["plan", "22:00=16", "6:30=20"], link)

        self.assertEqual((code, output, link.sent), (0, "06:30 20.0\n22:00 16.0\n", []))

    def test_missing_thermostat_exits_three(self):
        with mock.patch.dict(os.environ, {"HEARTH_PORT": os.path.join(os.sep, "nonexistent", "hearth")}):
            with contextlib.redirect_stderr(io.StringIO()):
                code = main(["status"])

        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
