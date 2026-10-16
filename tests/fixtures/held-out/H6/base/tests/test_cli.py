import contextlib
import io
import os
import unittest
from unittest import mock

from inkstrip.cli import main
from tests.fakes import RecordingPrinter


def run(argv, link):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv, open_printer=lambda: link)
    return code, output.getvalue()


class CliTest(unittest.TestCase):
    def test_preview_needs_no_printer(self):
        link = RecordingPrinter()

        code, output = run(["preview", "Mira Okafor"], link)

        self.assertEqual(code, 0)
        self.assertIn("|Mira Okafor             |", output)
        self.assertEqual(link.received, [])

    def test_print_sends_each_line_then_prints(self):
        link = RecordingPrinter("PRINTED")

        code, output = run(["print", "Mira Okafor", "12 Quay Street"], link)

        self.assertEqual((code, output), (0, "PRINTED\n"))
        self.assertEqual(link.received, ["TEXT Mira Okafor", "TEXT 12 Quay Street", "PRINT"])

    def test_feed_advances_one_label(self):
        link = RecordingPrinter()

        code, _ = run(["feed"], link)

        self.assertEqual((code, link.received), (0, ["FEED 28"]))

    def test_a_label_that_does_not_fit_sends_nothing(self):
        link = RecordingPrinter()

        code, _ = run(["print", "one", "two", "three", "four", "five"], link)

        self.assertEqual((code, link.received), (2, []))

    def test_missing_printer_exits_three(self):
        with mock.patch.dict(os.environ, {"INKSTRIP_PORT": os.path.join(os.sep, "nonexistent", "inkstrip")}):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main(["status"])

        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
