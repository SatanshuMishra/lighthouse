import contextlib
import io
import os
import shutil
import tempfile
import unittest

from inkstrip.cli import main
from tests.fakes import RecordingPrinter

TWO_LABELS = "Mira Okafor\n12 Quay Street\n\nTomas Reyes\n4 Mill Lane\nHolt\n"


def sheet_file(test, text):
    folder = tempfile.mkdtemp()
    test.addCleanup(shutil.rmtree, folder, True)
    path = os.path.join(folder, "labels.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def run(argv, link):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv, open_printer=lambda: link)
    return code, output.getvalue()


class SheetTest(unittest.TestCase):
    def test_sheet_prints_every_label_in_order(self):
        link = RecordingPrinter("PRINTED")

        code, output = run(["sheet", sheet_file(self, TWO_LABELS)], link)

        self.assertEqual((code, output), (0, "printed 2 labels\n"))
        self.assertEqual(
            [command for command in link.received if command.startswith("TEXT ")],
            ["TEXT Mira Okafor", "TEXT 12 Quay Street", "TEXT Tomas Reyes", "TEXT 4 Mill Lane", "TEXT Holt"],
        )
        self.assertEqual(link.received.count("PRINT"), 2)

    def test_each_printed_label_is_fed_on_before_the_next(self):
        link = RecordingPrinter("PRINTED")

        run(["sheet", sheet_file(self, TWO_LABELS)], link)

        self.assertEqual(
            [link.received[index + 1] for index, command in enumerate(link.received) if command == "PRINT"],
            ["FEED 28", "FEED 28"],
        )

    def test_a_label_that_does_not_fit_stops_the_run_before_printing(self):
        link = RecordingPrinter("PRINTED")

        code, _ = run(["sheet", sheet_file(self, TWO_LABELS + "\none\ntwo\nthree\nfour\nfive\n")], link)

        self.assertEqual((code, link.received), (2, []))


if __name__ == "__main__":
    unittest.main()
