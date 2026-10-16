import json
import os
import unittest

from tests import scratch


def feature_branch_two_commits_ahead(test):
    work, _ = scratch.make_repo(test)
    scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
    first = scratch.commit_files(work, {"a.py": "A = 1\n"}, "add a")
    second = scratch.commit_files(work, {"b.py": "B = 2\n"}, "add b\n\nb holds two")
    scratch.run_git(work, "push", "-q", "origin", "feat/x")
    scratch.run_git(work, "checkout", "-q", "main")
    scratch.commit_files(work, {"c.py": "C = 3\n"}, "add c on main")
    scratch.run_git(work, "push", "-q", "origin", "main")
    return work, first, second


def lighthouse_change(test, work, feature, answers):
    stubs = os.path.join(scratch.make_home(test), "stubs")
    scratch.stub_gh(stubs, answers)
    env = scratch.environment(scratch.make_home(test), stubs)
    code, stdout, stderr = scratch.run_lighthouse(
        ["change", "--repo", work, "--core", "main", "--feature", feature], env
    )
    return code, stdout, stderr, stubs


class ChangeTest(unittest.TestCase):
    def test_lists_commits_and_files(self):
        work, first, second = feature_branch_two_commits_ahead(self)

        code, stdout, stderr, _ = lighthouse_change(self, work, "feat/x", {})

        self.assertEqual(code, 0, stderr)
        change = json.loads(stdout)
        self.assertEqual(
            change["commits"],
            [
                {"sha": first, "subject": "add a", "body": ""},
                {"sha": second, "subject": "add b", "body": "b holds two"},
            ],
        )
        self.assertEqual(change["files"], ["a.py", "b.py"])
        self.assertEqual(change["feature_commit"], second)
        self.assertEqual((change["core"], change["feature"]), ("main", "feat/x"))

    def test_reads_merged_pull_requests(self):
        work, _, _ = feature_branch_two_commits_ahead(self)
        merged = [
            {"number": 1, "title": "feat(a): add a", "body": "a is the first half", "url": "https://example.invalid/1"},
            {"number": 2, "title": "feat(b): add b", "body": "b is the second half", "url": "https://example.invalid/2"},
        ]

        code, stdout, stderr, stubs = lighthouse_change(self, work, "feat/x", {"feat/x": merged, "main": []})

        self.assertEqual(code, 0, stderr)
        change = json.loads(stdout)
        self.assertEqual(change["pull_requests"], merged)
        self.assertIsNone(change["pull_requests_error"])
        with open(os.path.join(stubs, "gh-calls.jsonl"), encoding="utf-8") as calls:
            arguments = [json.loads(line) for line in calls]
        self.assertEqual(len(arguments), 1)
        self.assertEqual(arguments[0][:2], ["pr", "list"])
        self.assertEqual(arguments[0][arguments[0].index("--base") + 1], "feat/x")
        self.assertEqual(arguments[0][arguments[0].index("--state") + 1], "merged")

    def test_refuses_a_missing_branch(self):
        work, _ = scratch.make_repo(self)

        code, stdout, stderr, _ = lighthouse_change(self, work, "feat/none", {})

        self.assertEqual(code, 2)
        self.assertIn("feat/none", stderr)


if __name__ == "__main__":
    unittest.main()
