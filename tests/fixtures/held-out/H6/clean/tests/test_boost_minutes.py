import contextlib
import io
import unittest

from hearthctl.cli import main
from tests.fakes import FakeLink


class BoostMinutesTest(unittest.TestCase):
    def test_minutes_option_still_sends_one_boost_command(self):
        link = FakeLink("BOOSTING")

        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["boost", "--minutes", "45"], connect=lambda: link)

        self.assertEqual(code, 0)
        self.assertEqual(len(link.sent), 1)
        self.assertTrue(link.sent[0].startswith("BOOST "))


if __name__ == "__main__":
    unittest.main()
