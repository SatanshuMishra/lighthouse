import json
import os
import unittest

from tests import scratch

PROFILE_PATH = ".lighthouse/profile.json"


def profile_check(test, work):
    env = scratch.environment(scratch.make_home(test))
    code, stdout, stderr = scratch.run_lighthouse(["profile", "check", "--repo", work], env)
    return code, json.loads(stdout), stderr


def problem_kinds(report):
    return [problem["kind"] for problem in report["problems"]]


def details_of(report, kind):
    return [problem["detail"] for problem in report["problems"] if problem["kind"] == kind]


def checkout_state(work):
    return (
        scratch.run_git(work, "symbolic-ref", "HEAD").strip(),
        scratch.run_git(work, "rev-parse", "HEAD").strip(),
        scratch.run_git(work, "status", "--porcelain", "--untracked-files=all"),
        scratch.run_git(work, "worktree", "list", "--porcelain"),
    )


class ProfileCheckTest(unittest.TestCase):
    def test_accepts_a_healthy_profile(self):
        work, _ = scratch.make_repo(self)
        scratch.commit_files(
            work,
            {
                "pyproject.toml": "[project]\nname = \"scratch\"\n",
                ".github/workflows/ci.yml": "on: push\n",
                "scripts/sign_in.sh": "exit 0\n",
                "src/app.py": "print('app')\n",
            },
            "add the project files",
        )
        surface = {
            **scratch.sample_profile()["surfaces"][0],
            "paths": ["src/app.py", "README.md"],
            "sign_in": {"method": "command", "command": "APP_MODE=test sh scripts/sign_in.sh"},
            "credentials": ["APP_USER"],
        }
        scratch.write_profile(
            work,
            scratch.sample_profile(
                sources=["pyproject.toml", ".github/workflows/ci.yml"],
                surfaces=[surface],
                credentials={"file": None, "names": {"APP_USER": {"production": False}}},
                facts={"start_port": {"value": None, "confirmed": False, "recheck": "read src/app.py"}},
                build={"command": "python3 -m compileall -q src"},
                start={"command": "python3 src/app.py", "ready": "app"},
            ),
        )

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(report, {"ok": True, "problems": []})

    def test_reports_a_missing_profile(self):
        work, _ = scratch.make_repo(self)

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertFalse(report["ok"])
        self.assertEqual(problem_kinds(report), ["missing"])

    def test_reports_unreadable_json(self):
        work, _ = scratch.make_repo(self)
        os.makedirs(os.path.join(work, ".lighthouse"))
        with open(os.path.join(work, PROFILE_PATH), "w", encoding="utf-8") as handle:
            handle.write("{not json")

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertEqual(problem_kinds(report), ["malformed"])

    def test_reports_a_wrong_version(self):
        work, _ = scratch.make_repo(self)
        scratch.write_profile(work, scratch.sample_profile(version=99))

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertEqual(problem_kinds(report), ["version"])

    def test_reports_a_missing_field(self):
        work, _ = scratch.make_repo(self)
        profile = {key: value for key, value in scratch.sample_profile().items() if key != "surfaces"}
        scratch.write_profile(work, profile)

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertEqual(problem_kinds(report), ["schema"])
        self.assertIn("surfaces", details_of(report, "schema")[0])

    def test_reports_a_vanished_path(self):
        work, _ = scratch.make_repo(self)
        scratch.commit_files(work, {"src/old.py": "OLD = 1\n"}, "add old")
        scratch.run_git(work, "rm", "-q", "src/old.py")
        scratch.run_git(work, "commit", "-q", "-m", "remove old")
        surface = {**scratch.sample_profile()["surfaces"][0], "paths": ["src/old.py"]}
        scratch.write_profile(work, scratch.sample_profile(surfaces=[surface]))

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertEqual(problem_kinds(report), ["path"])
        self.assertIn("src/old.py", details_of(report, "path")[0])

    def test_reports_a_vanished_command(self):
        work, _ = scratch.make_repo(self)
        scratch.commit_files(work, {"scripts/test.sh": "exit 0\n"}, "add the test script")
        scratch.run_git(work, "rm", "-q", "scripts/test.sh")
        scratch.run_git(work, "commit", "-q", "-m", "remove the test script")
        suite = {"command": "sh scripts/test.sh", "junit": None, "timeout_minutes": None}
        scratch.write_profile(work, scratch.sample_profile(suite=suite))

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertEqual(problem_kinds(report), ["command"])
        self.assertIn("scripts/test.sh", details_of(report, "command")[0])

    def test_reports_an_unrecorded_source(self):
        work, _ = scratch.make_repo(self)
        scratch.commit_files(work, {"package.json": "{}\n"}, "add a package manifest")
        scratch.write_profile(work, scratch.sample_profile())

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertEqual(problem_kinds(report), ["unrecorded"])
        self.assertIn("package.json", details_of(report, "unrecorded")[0])

    def test_accepts_pattern_arguments(self):
        work, _ = scratch.make_repo(self)
        scratch.commit_files(work, {"docs/index_test.py": "\n"}, "add the docs folder")
        command = "cd docs && python3 -m unittest discover -p '*_test.py' && echo ./... src/**/*.ts"
        suite = {"command": command, "junit": None, "timeout_minutes": None}
        scratch.write_profile(work, scratch.sample_profile(suite=suite))

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(report, {"ok": True, "problems": []})


class ProfilePublishTest(unittest.TestCase):
    def test_publish_commits_to_the_feature_branch(self):
        work, remote = scratch.make_repo(self)
        scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
        scratch.commit_files(work, {"a.py": "A = 1\n"}, "add a")
        scratch.run_git(work, "push", "-q", "origin", "feat/x")
        scratch.run_git(work, "checkout", "-q", "main")
        before_publish = scratch.run_git(remote, "rev-parse", "feat/x").strip()
        fact = {"value": None, "confirmed": False, "recheck": "read the start script"}
        scratch.write_profile(work, scratch.sample_profile(facts={"start_port": fact}))
        home = scratch.make_home(self)
        state = os.path.join(home, ".lighthouse", os.path.basename(work))
        os.makedirs(state, mode=0o700)
        with open(os.path.join(state, "answers.json"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"start_port": "8080"}))
        checkout_before = checkout_state(work)

        code, stdout, stderr = scratch.run_lighthouse(
            ["profile", "publish", "--repo", work, "--feature", "feat/x"], scratch.environment(home)
        )

        self.assertEqual(code, 0, stderr)
        published = scratch.run_git(remote, "rev-parse", "feat/x").strip()
        self.assertEqual(json.loads(stdout), {"committed": True, "commit": published})
        self.assertEqual(scratch.run_git(remote, "rev-list", "{}..{}".format(before_publish, published)).split(), [published])
        self.assertEqual(scratch.run_git(remote, "rev-parse", published + "^").strip(), before_publish)
        changed = scratch.run_git(remote, "diff-tree", "--no-commit-id", "--name-only", "-r", published).split()
        self.assertEqual(changed, [PROFILE_PATH])
        self.assertEqual(
            scratch.run_git(remote, "log", "-1", "--format=%s", published).strip(),
            "chore(lighthouse): record the test profile",
        )
        committed = json.loads(scratch.run_git(remote, "show", "{}:{}".format(published, PROFILE_PATH)))
        self.assertEqual(
            committed["facts"]["start_port"],
            {"value": "8080", "confirmed": True, "recheck": "read the start script"},
        )
        self.assertEqual(checkout_state(work), checkout_before)

    def test_publish_refuses_a_checked_out_branch_without_a_remote(self):
        work, _ = scratch.make_repo(self)
        scratch.run_git(work, "remote", "remove", "origin")
        scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
        scratch.commit_files(work, {"a.py": "A = 1\n"}, "add a")
        feature_before = scratch.run_git(work, "rev-parse", "refs/heads/feat/x").strip()
        scratch.write_profile(work, scratch.sample_profile())
        checkout_before = checkout_state(work)

        code, stdout, stderr = scratch.run_lighthouse(
            ["profile", "publish", "--repo", work, "--feature", "feat/x"],
            scratch.environment(scratch.make_home(self)),
        )

        self.assertEqual(code, 2, stderr)
        self.assertIn("feat/x", json.loads(stdout)["error"])
        self.assertEqual(scratch.run_git(work, "rev-parse", "refs/heads/feat/x").strip(), feature_before)
        self.assertEqual(checkout_state(work), checkout_before)


if __name__ == "__main__":
    unittest.main()
