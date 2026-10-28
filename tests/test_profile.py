import json
import os
import time
import unittest

from tests import scratch

PROFILE_PATH = ".lighthouse/profile.json"
EXITED_START_SECONDS = 8
MEASURED_UPGRADE = {"field": "measured", "detail": "measured is not set, and lighthouse:doctor writes it"}


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
            "reach": "python3 --version",
        }
        measured = {
            "commit": scratch.run_git(work, "rev-parse", "HEAD").strip(),
            "measured_at": "2026-10-28T00:00:00.000Z",
            "setup_seconds": None,
            "build_seconds": 0.5,
            "suite_seconds": 12.25,
            "suite_exit": 0,
            "start_seconds": None,
            "ready": False,
            "drivers": {"cli": {"seconds": 0.01, "exit": 0}},
        }
        scratch.write_profile(
            work,
            scratch.sample_profile(
                sources=["pyproject.toml", ".github/workflows/ci.yml"],
                suite={**scratch.sample_profile()["suite"], "rerun": "python3 -m unittest {tests}", "isolated": True},
                surfaces=[surface],
                credentials={"file": None, "names": {"APP_USER": {"production": False}}},
                facts={"start_port": {"value": None, "confirmed": False, "recheck": "read src/app.py"}},
                build={"command": "python3 -m compileall -q src"},
                start={"command": "python3 src/app.py", "ready": "app"},
                measured=measured,
            ),
        )

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(report, {"ok": True, "problems": [], "upgrades": []})

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
        suite = {"command": command, "junit": None, "timeout_minutes": None, "rerun": None, "isolated": False}
        scratch.write_profile(work, scratch.sample_profile(suite=suite))

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(report, {"ok": True, "problems": [], "upgrades": [MEASURED_UPGRADE]})

    def test_reports_a_vanished_setup_script(self):
        work, _ = scratch.make_repo(self)
        scratch.write_profile(work, scratch.sample_profile(setup={"command": "sh scripts/install_deps.sh"}))

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertEqual(problem_kinds(report), ["command"])
        self.assertIn("scripts/install_deps.sh", details_of(report, "command")[0])

    def test_resolves_paths_after_cd(self):
        work, _ = scratch.make_repo(self)
        scratch.commit_files(work, {"web/run.sh": "exit 0\n", "tools/check.py": "\n"}, "add the scripts")
        os.chmod(os.path.join(work, "web", "run.sh"), 0o755)
        suite = {"command": "cd web && ./run.sh", "junit": None, "timeout_minutes": None, "rerun": None, "isolated": False}
        build = {"command": "cd tools && python3 check.py"}
        scratch.write_profile(work, scratch.sample_profile(suite=suite, build=build))

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(report, {"ok": True, "problems": [], "upgrades": [MEASURED_UPGRADE]})

    def test_accepts_shell_builtins_and_keywords(self):
        work, _ = scratch.make_repo(self)
        suite = {
            "command": "unset CI && exec python3 -m unittest",
            "junit": None,
            "timeout_minutes": None,
            "rerun": None,
            "isolated": False,
        }
        build = {"command": "{ : ; eval true; } && if test -d src; then umask 022; fi"}
        scratch.write_profile(work, scratch.sample_profile(suite=suite, build=build))

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(report, {"ok": True, "problems": [], "upgrades": [MEASURED_UPGRADE]})


    def test_profile_accepts_rerun(self):
        work, _ = scratch.make_repo(self)
        suite = {**scratch.sample_profile()["suite"], "rerun": "pytest --lf"}
        scratch.write_profile(work, scratch.sample_profile(suite=suite))

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertTrue(report["ok"])
        self.assertEqual(report["problems"], [])


    def test_profile_rejects_a_rerun_placeholder_inside_quotes(self):
        work, _ = scratch.make_repo(self)
        for rerun in ('go test -run "{names_regex}"', "pytest '{tests}'"):
            with self.subTest(rerun=rerun):
                suite = {**scratch.sample_profile()["suite"], "rerun": rerun}
                scratch.write_profile(work, scratch.sample_profile(suite=suite))

                code, report, _ = profile_check(self, work)

                self.assertEqual(code, 1)
                self.assertEqual(problem_kinds(report), ["rerun"])

    def test_profile_accepts_isolated(self):
        work, _ = scratch.make_repo(self)
        suite = {**scratch.sample_profile()["suite"], "isolated": True}
        scratch.write_profile(work, scratch.sample_profile(suite=suite))

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertTrue(report["ok"])
        self.assertEqual(report["problems"], [])

    def test_profile_rejects_a_non_boolean_isolated(self):
        work, _ = scratch.make_repo(self)
        suite = {**scratch.sample_profile()["suite"], "isolated": "yes"}
        scratch.write_profile(work, scratch.sample_profile(suite=suite))

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertEqual(problem_kinds(report), ["schema"])
        self.assertIn("suite.isolated", details_of(report, "schema")[0])

    def test_profile_lists_missing_suite_fields_as_upgrades(self):
        work, _ = scratch.make_repo(self)
        scratch.write_profile(work, scratch.sample_profile())

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(report["problems"], [])
        self.assertEqual([item["field"] for item in report["upgrades"]], ["suite.rerun", "suite.isolated", "measured"])

    def test_profile_rejects_a_mistyped_measurement(self):
        work, _ = scratch.make_repo(self)
        scratch.write_profile(work, scratch.sample_profile(measured={"suite_exit": "passed"}))

        code, report, _ = profile_check(self, work)

        self.assertEqual(code, 1)
        self.assertEqual(problem_kinds(report), ["schema"])
        self.assertIn("measured.suite_exit", details_of(report, "schema")[0])

    def test_unresolvable_reach_is_not_a_problem(self):
        work, _ = scratch.make_repo(self)
        surface = {**scratch.sample_profile()["surfaces"][0], "reach": "no-such-lighthouse-program --version"}
        scratch.write_profile(work, scratch.sample_profile(surfaces=[surface]))

        code, report, stderr = profile_check(self, work)

        self.assertEqual(code, 0, stderr)
        self.assertEqual(report["problems"], [])


class ProfileMeasureTest(unittest.TestCase):
    def measure(self, work, *extra):
        env = scratch.environment(scratch.make_home(self))
        code, stdout, _ = scratch.run_lighthouse(["profile", "measure", "--repo", work, *extra], env)
        return code, json.loads(stdout)

    def test_measure_refuses_a_missing_profile(self):
        work, _ = scratch.make_repo(self)

        code, printed = self.measure(work)

        self.assertEqual(code, 2)
        self.assertIn("no readable profile", printed["error"])

    def test_measure_refuses_a_profile_without_a_suite_command(self):
        work, _ = scratch.make_repo(self)
        scratch.write_profile(work, scratch.sample_profile(suite={"junit": None, "timeout_minutes": None}))

        code, printed = self.measure(work)

        self.assertEqual(code, 2)
        self.assertIn("no suite command", printed["error"])

    def test_measure_waits_for_a_log_line_and_replaces_an_old_measurement(self):
        work, _ = scratch.make_repo(self)
        missing = {**scratch.sample_profile()["surfaces"][0], "name": "missing", "reach": "no-such-lighthouse-program"}
        profile = scratch.sample_profile(
            suite={"command": "exit 3", "junit": None, "timeout_minutes": None},
            setup={"command": "true"},
            start={"command": "echo serving now && exec sleep 30", "ready": "serving now"},
            surfaces=[scratch.sample_profile()["surfaces"][0], missing],
            measured={"suite_seconds": 0.001, "suite_exit": 0, "drivers": {"stale": {"seconds": 1, "exit": 0}}},
        )
        scratch.write_profile(work, profile)

        code, printed = self.measure(work)

        self.assertEqual(code, 0, printed)
        measured = printed["measured"]
        self.assertEqual(measured["suite_exit"], 3)
        self.assertIsInstance(measured["setup_seconds"], float)
        self.assertIsNone(measured["build_seconds"])
        self.assertIs(measured["ready"], True)
        self.assertEqual(sorted(measured["drivers"]), ["missing"])
        self.assertEqual(printed["available"], {"cli": True, "missing": False})
        with open(os.path.join(work, PROFILE_PATH), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["measured"], measured)

    def test_measure_stops_waiting_once_the_start_command_exits(self):
        work, _ = scratch.make_repo(self)
        missing = os.path.join(scratch.temporary_folder(self, "lh-ready-"), "never-written")
        profile = scratch.sample_profile(
            suite={"command": "true", "junit": None, "timeout_minutes": 0.25},
            start={"command": "exit 1", "ready": "test -f {}".format(missing)},
        )
        scratch.write_profile(work, profile)
        started = time.monotonic()

        code, printed = self.measure(work)

        self.assertLess(time.monotonic() - started, EXITED_START_SECONDS)
        self.assertEqual(code, 0, printed)
        self.assertIs(printed["measured"]["ready"], False)
        self.assertIsNone(printed["measured"]["start_seconds"])


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


    def test_publish_refuses_a_linked_profile_path(self):
        work, _ = scratch.make_repo(self)
        outside = scratch.temporary_folder(self, "lh-outside-")
        victim = os.path.join(outside, "victim.txt")
        with open(victim, "w", encoding="utf-8") as handle:
            handle.write("keep\n")
        scratch.run_git(work, "checkout", "-q", "-b", "feat/x")
        os.makedirs(os.path.join(work, ".lighthouse"))
        os.symlink(victim, os.path.join(work, PROFILE_PATH))
        scratch.run_git(work, "add", "-A")
        scratch.run_git(work, "commit", "-q", "-m", "link the profile")
        scratch.run_git(work, "push", "-q", "origin", "feat/x")
        scratch.run_git(work, "checkout", "-q", "main")
        profile_file = os.path.join(outside, "profile.json")
        with open(profile_file, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(scratch.sample_profile()))

        code, stdout, stderr = scratch.run_lighthouse(
            ["profile", "publish", "--repo", work, "--feature", "feat/x", "--profile", profile_file],
            scratch.environment(scratch.make_home(self)),
        )

        self.assertEqual(code, 2, stderr)
        self.assertIn("symbolic link", json.loads(stdout)["error"])
        with open(victim, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "keep\n")

if __name__ == "__main__":
    unittest.main()
