import os
import unittest

from tests import scratch

MARKERS = os.path.join(scratch.ROOT, "tests", "fixtures", "held-out", "LEAK_MARKERS")
TUNED_FOLDERS = ("skills", "lighthouse_tool")


def leak_markers():
    with open(MARKERS, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def tuned_files():
    return sorted(
        os.path.join(folder, name)
        for top in TUNED_FOLDERS
        for folder, _, names in os.walk(os.path.join(scratch.ROOT, top))
        for name in names
    )


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class LeakTest(unittest.TestCase):
    def test_held_out_cases_do_not_leak(self):
        markers = leak_markers()
        files = tuned_files()
        self.assertTrue(markers)
        self.assertTrue(files)

        leaks = [
            "{} holds {}".format(os.path.relpath(path, scratch.ROOT), marker)
            for path in files
            for content in [read_bytes(path)]
            for marker in markers
            if marker.encode("utf-8") in content
        ]

        self.assertEqual(leaks, [])


if __name__ == "__main__":
    unittest.main()
