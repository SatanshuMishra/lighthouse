import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from jotbook.cli import main


def run(argv):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(argv)
    return code, output.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = folder.name

    def test_add_then_list_with_the_store_option(self):
        path = os.path.join(self.folder, "notes.json")

        run(["add", "--store", path, "buy milk"])
        code, output = run(["list", "--store", path])

        self.assertEqual(code, 0)
        self.assertEqual(output, "1. buy milk\n")

    def test_uses_the_environment_file_without_the_option(self):
        path = os.path.join(self.folder, "default.json")
        with mock.patch.dict(os.environ, {"JOTBOOK_FILE": path}):
            run(["add", "call the plumber"])
            code, output = run(["list"])

        self.assertEqual(code, 0)
        self.assertEqual(output, "1. call the plumber\n")


if __name__ == "__main__":
    unittest.main()
