import contextlib
import io
import os
import unittest
from unittest import mock

from inkstrip.cli import main
from tests.fakes import FakeLink


def run(argv, link):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv, connect=lambda: link)
    return code, output.getvalue()


class CliTest(unittest.TestCase):
    def test_preview_needs_no_printer(self):
        link = FakeLink()

        code, output = run(["preview", "Mira Okafor"], link)

        self.assertEqual(code, 0)
        self.assertIn("|Mira Okafor             |", output)
        self.assertEqual(link.sent, [])

    def test_print_feeds_the_printed_label_out_to_the_tear_bar(self):
        link = FakeLink("PRINTED")

        code, output = run(["print", "Mira Okafor", "12 Quay Street"], link)

        self.assertEqual((code, output), (0, "PRINTED\n"))
        self.assertEqual(link.sent, ["TEXT Mira Okafor", "TEXT 12 Quay Street", "PRINT", "FEED 28"])

    def test_feed_advances_one_label(self):
        link = FakeLink()

        code, _ = run(["feed"], link)

        self.assertEqual((code, link.sent), (0, ["FEED 28"]))

    def test_a_label_that_does_not_fit_sends_nothing(self):
        link = FakeLink()

        code, _ = run(["print", "one", "two", "three", "four", "five"], link)

        self.assertEqual((code, link.sent), (2, []))

    def test_missing_printer_exits_three(self):
        with mock.patch.dict(os.environ, {"INKSTRIP_PORT": os.path.join(os.sep, "nonexistent", "inkstrip")}):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main(["status"])

        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
