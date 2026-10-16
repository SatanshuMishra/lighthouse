import os
import unittest

from tests import scratch


def write_files(folder, files):
    for relative_path, text in files.items():
        path = os.path.join(folder, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    return folder


class HeldOutChecksTest(unittest.TestCase):
    def test_names_each_retired_marker_a_folder_holds(self):
        from tests import held_out_checks

        folder = write_files(
            scratch.temporary_folder(self, "lh-held-out-"),
            {"a.txt": "Run JOTBOOK add", os.path.join("sub", "b.txt"): "nothing to see"},
        )

        self.assertEqual(held_out_checks.retired_markers_in(folder), ["a.txt holds jotbook"])

    def test_names_each_schema_problem(self):
        from tests import held_out_checks

        fixture = {
            "kind": "library",
            "feature": "feature/x",
            "suite": "true",
            "changes": ["change-1", "change-2"],
            "clean": {"change-2": "clean"},
            "pull_requests": [{"title": "feat: a", "body": "A."}, {"title": "feat: b", "body": "B."}],
            "surfaces": ["x"],
            "expect": {"broken": "green", "clean": "green"},
        }

        problems = held_out_checks.schema_problems(fixture)

        self.assertCountEqual(
            [("markers" in sentence, "expect" in sentence) for sentence in problems],
            [(True, False), (False, True)],
        )

    def test_names_a_profile_in_a_fixture_that_must_start_without_one(self):
        from tests import held_out_checks

        folder = write_files(
            scratch.temporary_folder(self, "lh-held-out-"),
            {os.path.join("base", ".lighthouse", "profile.json"): "{}"},
        )
        fixture = {"expect": {"broken": "failures", "clean": "green"}}

        problems = held_out_checks.profile_problems(folder, fixture)

        self.assertEqual(len(problems), 1, problems)
        self.assertIn(".lighthouse/profile.json", problems[0])

    def test_names_a_device_profile_that_marks_nothing_unavailable(self):
        from tests import held_out_checks

        folder = write_files(
            scratch.temporary_folder(self, "lh-held-out-"),
            {
                os.path.join("base", ".lighthouse", "profile.json"): (
                    '{"version": 1, "surfaces": [{"name": "d", "available": true}], "off_limits": ["x"]}'
                )
            },
        )
        fixture = {"expect": {"broken": "not-green", "clean": "not-green"}}

        problems = held_out_checks.profile_problems(folder, fixture)

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("available", problems[0])

    def test_accepts_a_well_formed_fixture(self):
        from tests import held_out_checks

        fixture = {
            "kind": "library",
            "feature": "feature/x",
            "suite": "true",
            "changes": ["change-1", "change-2"],
            "clean": {"change-2": "clean"},
            "pull_requests": [{"title": "feat: a", "body": "A."}, {"title": "feat: b", "body": "B."}],
            "markers": ["x"],
            "surfaces": ["x"],
            "expect": {"broken": "failures", "clean": "green"},
        }

        self.assertEqual(held_out_checks.schema_problems(fixture), [])


if __name__ == "__main__":
    unittest.main()
