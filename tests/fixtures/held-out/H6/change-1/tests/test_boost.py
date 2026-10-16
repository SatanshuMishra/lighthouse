import contextlib
import io
import unittest

from hearthctl.cli import main
from tests.fakes import FakeLink


class BoostTest(unittest.TestCase):
    def test_boost_sends_one_boost_command(self):
        link = FakeLink("BOOSTING")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            code = main(["boost"], connect=lambda: link)

        self.assertEqual((code, output.getvalue()), (0, "BOOSTING\n"))
        self.assertEqual(len(link.sent), 1)
        self.assertTrue(link.sent[0].startswith("BOOST "))


if __name__ == "__main__":
    unittest.main()
