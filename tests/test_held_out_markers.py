import os
import unittest

from tests import scratch

MARKERS = os.path.join(scratch.ROOT, "tests", "fixtures", "held-out", "LEAK_MARKERS")
MARKERS_PER_FIXTURE = 3


def leak_markers():
    with open(MARKERS, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


class HeldOutMarkersTest(unittest.TestCase):
    def test_leak_markers_name_only_the_new_set(self):
        from tests import e2e_harness, held_out_checks

        markers = leak_markers()
        fixture_texts = {
            fid: "\n".join(e2e_harness.tree_files(os.path.join(e2e_harness.FIXTURES, fid)).values())
            for fid in e2e_harness.fixture_ids()
        }
        self.assertTrue(markers)
        self.assertTrue(fixture_texts)

        retired = [marker for marker in markers if marker in held_out_checks.RETIRED_MARKERS]
        thin = {
            fid: found
            for fid, text in fixture_texts.items()
            for found in [[marker for marker in markers if marker in text]]
            if len(found) < MARKERS_PER_FIXTURE
        }
        unfound = [marker for marker in markers if not any(marker in text for text in fixture_texts.values())]

        self.assertEqual(retired, [])
        self.assertEqual(thin, {})
        self.assertEqual(unfound, [])


if __name__ == "__main__":
    unittest.main()
