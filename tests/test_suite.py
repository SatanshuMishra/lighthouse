import json
import os
import shutil
import unittest

from tests import scratch

JUNIT_SUITE = """set -e
if [ -f reports/$LIGHTHOUSE_BUILD-rerun.xml ] && [ -f .first-run-done ]; then
  cp reports/$LIGHTHOUSE_BUILD-rerun.xml report.xml
else
  cp reports/$LIGHTHOUSE_BUILD.xml report.xml
fi
touch .first-run-done
"""


def junit(outcomes):
    cases = "".join(
        '<testcase classname="tests.T" name="{}">{}</testcase>'.format(
            name, '<failure message="boom"/>' if outcome == "failed" else ""
        )
        for name, outcome in outcomes.items()
    )
    return '<?xml version="1.0"?><testsuite name="tests">{}</testsuite>\n'.format(cases)


def project_with(test, files, profile):
    work, _ = scratch.make_repo(test)
    scratch.write_profile(work, profile)
    scratch.commit_files(work, {**files, ".lighthouse/profile.json": read(work, ".lighthouse/profile.json")}, "add the project")
    scratch.run_git(work, "push", "-q", "origin", "main")
    scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
    scratch.commit_files(work, {"feature.txt": "the feature\n"}, "add the feature")
    scratch.run_git(work, "push", "-q", "-u", "origin", "feat/x")
    scratch.run_git(work, "checkout", "-q", "main")
    return work


def junit_project(test, reports):
    files = {"suite.sh": JUNIT_SUITE}
    report_files = {"reports/{}.xml".format(name): junit(outcomes) for name, outcomes in reports.items()}
    profile = scratch.sample_profile(suite={"command": "sh suite.sh", "junit": "report.xml", "timeout_minutes": None})
    return project_with(test, {**files, **report_files}, profile)


def read(repo, relative_path):
    with open(os.path.join(repo, relative_path), encoding="utf-8") as handle:
        return handle.read()


def lighthouse(test, subcommand, work, results, *extra):
    env = scratch.environment(scratch.make_home(test))
    branches = ["--core", "main", "--feature", "feat/x"] if subcommand != "release" else []
    return scratch.run_lighthouse([subcommand, "--repo", work, *branches, "--results", results, *extra], env)


def results_folder(test):
    return os.path.join(scratch.make_home(test), "results")


def suite_of(test, work):
    results = results_folder(test)
    code, stdout, stderr = lighthouse(test, "suite", work, results)
    test.assertEqual(code, 0, stderr)
    return json.loads(stdout)


def head_of(worktree):
    return scratch.run_git(worktree, "rev-parse", "HEAD").strip()


def is_detached(worktree):
    return scratch.run_git(worktree, "rev-parse", "--abbrev-ref", "HEAD").strip() == "HEAD"


def listed_worktrees(work):
    porcelain = scratch.run_git(work, "worktree", "list", "--porcelain")
    return [os.path.realpath(line[len("worktree "):]) for line in porcelain.splitlines() if line.startswith("worktree ")]


class SuiteTest(unittest.TestCase):
    def test_counts_a_new_failure(self):
        work = junit_project(
            self,
            {
                "core": {"test_a": "passed", "test_b": "passed"},
                "feature": {"test_a": "passed", "test_b": "failed"},
            },
        )
        result = suite_of(self, work)
        self.assertEqual(result["result"], "failures")
        self.assertEqual(result["failures"], ["tests.T.test_b"])
        self.assertEqual(result["pre_existing"], [])
        self.assertEqual(result["flaky"], [])

    def test_pre_existing_failures_are_not_new(self):
        work = junit_project(
            self,
            {
                "core": {"test_a": "passed", "test_c": "failed"},
                "feature": {"test_a": "passed", "test_c": "failed"},
            },
        )
        result = suite_of(self, work)
        self.assertEqual(result["pre_existing"], ["tests.T.test_c"])
        self.assertNotIn("tests.T.test_c", result["failures"])
        self.assertEqual(result["result"], "passed")

    def test_compares_by_exit_status_without_a_report(self):
        profile = scratch.sample_profile(
            suite={"command": 'test "$LIGHTHOUSE_BUILD" = core', "junit": None, "timeout_minutes": None}
        )
        work = project_with(self, {}, profile)
        result = suite_of(self, work)
        self.assertEqual(result["result"], "failures")
        self.assertEqual(result["failures"], ["suite"])
        self.assertEqual(result["core"]["exit"], 0)
        self.assertEqual(result["feature"]["exit"], 1)

    def test_blocked_when_the_suite_cannot_start(self):
        command = 'if [ "$LIGHTHOUSE_BUILD" = feature ]; then lighthouse-no-such-program; fi'
        profile = scratch.sample_profile(suite={"command": command, "junit": None, "timeout_minutes": None})
        work = project_with(self, {}, profile)
        result = suite_of(self, work)
        self.assertEqual(result["result"], "blocked")
        self.assertEqual(result["failures"], [])

    def test_leaves_the_checkout_alone(self):
        work = junit_project(
            self,
            {
                "core": {"test_a": "passed"},
                "feature": {"test_a": "failed"},
            },
        )
        with open(os.path.join(work, "README.md"), "a", encoding="utf-8") as handle:
            handle.write("an uncommitted edit\n")

        def snapshot():
            return (
                scratch.run_git(work, "symbolic-ref", "HEAD").strip(),
                head_of(work),
                scratch.run_git(work, "status", "--porcelain"),
            )

        before = snapshot()
        results = results_folder(self)
        for subcommand in ("worktrees", "suite", "release"):
            code, _, stderr = lighthouse(self, subcommand, work, results)
            self.assertEqual(code, 0, stderr)
        self.assertEqual(snapshot(), before)
        self.assertEqual(before[0], "refs/heads/main")
        self.assertIn(" M README.md", before[2])

    def test_worktrees_use_the_remote_tips(self):
        work, _ = scratch.make_repo(self)
        scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
        local_tip = scratch.commit_files(work, {"a.txt": "a\n"}, "add a")
        remote_tip = scratch.commit_files(work, {"b.txt": "b\n"}, "add b")
        scratch.run_git(work, "push", "-q", "origin", "feat/x")
        scratch.run_git(work, "checkout", "-q", "main")
        scratch.run_git(work, "branch", "-f", "feat/x", local_tip)
        results = results_folder(self)
        code, stdout, stderr = lighthouse(self, "worktrees", work, results)
        self.assertEqual(code, 0, stderr)
        feature = os.path.join(os.path.realpath(results), "feature")
        self.assertEqual(head_of(feature), remote_tip)
        self.assertTrue(is_detached(feature))
        self.assertEqual(json.loads(stdout)["feature"], {"path": feature, "commit": remote_tip})

    def test_release_removes_both_worktrees(self):
        work = project_with(self, {}, scratch.sample_profile())
        results = results_folder(self)
        code, _, stderr = lighthouse(self, "worktrees", work, results)
        self.assertEqual(code, 0, stderr)
        paths = [os.path.join(os.path.realpath(results), build) for build in ("core", "feature")]
        code, stdout, stderr = lighthouse(self, "release", work, results)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["removed"], paths)
        for path in paths:
            self.assertFalse(os.path.exists(path))
            self.assertNotIn(path, listed_worktrees(work))

    def test_worktrees_move_to_a_new_tip(self):
        work = project_with(self, {}, scratch.sample_profile())
        results = results_folder(self)
        code, _, stderr = lighthouse(self, "worktrees", work, results)
        self.assertEqual(code, 0, stderr)
        scratch.run_git(work, "checkout", "-q", "feat/x")
        new_tip = scratch.commit_files(work, {"later.txt": "later\n"}, "add a later change")
        scratch.run_git(work, "push", "-q", "origin", "feat/x")
        scratch.run_git(work, "checkout", "-q", "main")
        code, _, stderr = lighthouse(self, "worktrees", work, results)
        self.assertEqual(code, 0, stderr)
        feature = os.path.join(os.path.realpath(results), "feature")
        self.assertEqual(head_of(feature), new_tip)
        self.assertTrue(is_detached(feature))

    def test_runs_setup_and_build_before_the_suite(self):
        profile = scratch.sample_profile(
            setup={"command": "touch setup.done"},
            build={"command": "touch build.done"},
            suite={"command": "test -f setup.done && test -f build.done", "junit": None, "timeout_minutes": None},
        )
        work = project_with(self, {}, profile)
        result = suite_of(self, work)
        self.assertEqual(result["result"], "passed")
        self.assertEqual(result["core"]["exit"], 0)
        self.assertEqual(result["feature"]["exit"], 0)

    def test_blocked_when_feature_does_not_build(self):
        profile = scratch.sample_profile(build={"command": 'test "$LIGHTHOUSE_BUILD" = core'})
        work = project_with(self, {}, profile)
        result = suite_of(self, work)
        self.assertEqual(result["result"], "blocked")
        self.assertIn("build", result["reason"])

    def test_a_failure_that_passes_on_rerun_is_flaky(self):
        work = junit_project(
            self,
            {
                "core": {"test_d": "passed"},
                "feature": {"test_d": "failed"},
                "feature-rerun": {"test_d": "passed"},
            },
        )
        result = suite_of(self, work)
        self.assertEqual(result["flaky"], ["tests.T.test_d"])
        self.assertNotIn("tests.T.test_d", result["failures"])
        self.assertEqual(result["result"], "passed")

    def test_a_failing_exit_with_no_failed_test_is_a_failure(self):
        profile = scratch.sample_profile(
            suite={
                "command": "cp reports/clean.xml report.xml && test \"$LIGHTHOUSE_BUILD\" = core",
                "junit": "report.xml",
                "timeout_minutes": None,
            }
        )
        work = project_with(self, {"reports/clean.xml": junit({"test_a": "passed"})}, profile)
        result = suite_of(self, work)
        self.assertEqual(result["result"], "failures")
        self.assertEqual(result["failures"], ["suite"])

    def test_refuses_a_worktree_it_did_not_create(self):
        work = project_with(self, {}, scratch.sample_profile())
        results = results_folder(self)
        user_worktree = os.path.join(results, "feature")
        scratch.run_git(work, "worktree", "add", "-q", user_worktree, "feat/x")
        with open(os.path.join(user_worktree, "feature.txt"), "w", encoding="utf-8") as handle:
            handle.write("unsaved work\n")
        for subcommand in ("worktrees", "suite"):
            code, _, stderr = lighthouse(self, subcommand, work, results)
            self.assertEqual(code, 2)
            self.assertIn("did not create", stderr)
        code, stdout, stderr = lighthouse(self, "release", work, results)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn(os.path.realpath(user_worktree), json.loads(stdout)["removed"])
        self.assertEqual(read(user_worktree, "feature.txt"), "unsaved work\n")
        self.assertFalse(is_detached(user_worktree))

    def test_recovers_after_the_results_folder_is_deleted(self):
        work = project_with(self, {}, scratch.sample_profile())
        results = results_folder(self)
        code, _, stderr = lighthouse(self, "worktrees", work, results)
        self.assertEqual(code, 0, stderr)
        shutil.rmtree(results)
        code, _, stderr = lighthouse(self, "worktrees", work, results)
        self.assertEqual(code, 0, stderr)
        self.assertTrue(is_detached(os.path.join(os.path.realpath(results), "feature")))

    def test_suite_logs_hide_credential_values(self):
        planted = "s3cret-value"
        profile = scratch.sample_profile(
            suite={"command": 'echo "signing in with $APP_PASSWORD"', "junit": None, "timeout_minutes": None},
            credentials={"file": None, "names": {"APP_PASSWORD": {"production": False}}},
        )
        work = project_with(self, {}, profile)
        results = results_folder(self)
        env = {**scratch.environment(scratch.make_home(self)), "APP_PASSWORD": planted}
        code, _, stderr = scratch.run_lighthouse(
            ["suite", "--repo", work, "--core", "main", "--feature", "feat/x", "--results", results], env
        )
        self.assertEqual(code, 0, stderr)
        for build in ("core", "feature"):
            log = read(results, "suite-{}.log".format(build))
            self.assertIn("signing in with", log)
            self.assertNotIn(planted, log)


if __name__ == "__main__":
    unittest.main()
