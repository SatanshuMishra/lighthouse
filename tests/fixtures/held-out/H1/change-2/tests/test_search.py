import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from jotbook import notes
from jotbook.cli import main


def run(argv):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(argv)
    return code, output.getvalue()


class SearchTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "notes.json")
        notes.append(self.path, "buy milk")
        notes.append(self.path, "call the plumber")
        notes.append(self.path, "Milk the goat")

    def test_prints_matching_notes_with_their_numbers(self):
        with mock.patch.dict(os.environ, {"JOTBOOK_FILE": self.path}):
            code, output = run(["search", "MILK"])

        self.assertEqual(code, 0)
        self.assertEqual(output, "1. buy milk\n3. Milk the goat\n")

    def test_exits_one_when_nothing_matches(self):
        with mock.patch.dict(os.environ, {"JOTBOOK_FILE": self.path}):
            code, output = run(["search", "bread"])

        self.assertEqual(code, 1)
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
