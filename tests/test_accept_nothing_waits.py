import json
import os
import stat
import unittest

from tests import accept_support as support
from tests import scratch

TYPED = support.TYPED
CREDENTIAL_PASSWORD = "s3cret-value"


def build_flags(repo, results):
    return ["--repo", repo, "--core", "main", "--feature", "feature", "--results", results]


def recorded_suite(recorder, name, *keys):
    return {"command": recorder.command(name, *keys), "junit": None}


def credentials_profile():
    base = scratch.sample_profile()
    surface = {**base["surfaces"][0], "credentials": ["APP_PASSWORD"]}
    suite = {key: value for key, value in base["suite"].items() if key != "timeout_minutes"}
    return scratch.sample_profile(
        suite=suite,
        surfaces=[surface],
        credentials={"file": None, "names": {"APP_USER": {"production": False}, "APP_PASSWORD": {"production": False}}},
    )


def write_credentials(home, repo):
    path = os.path.join(home, ".lighthouse", os.path.basename(repo), "credentials.env")
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("APP_USER=tester\nAPP_PASSWORD={}\n".format(CREDENTIAL_PASSWORD))
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


class NothingWaits(unittest.TestCase):
    def test_step_shells_get_no_input(self):
        repo, _ = support.feature_repo(self)
        stubs = support.Stubs(self)
        recorder = support.Recorder(self)
        env = support.environment(self, stubs.folder)
        inputs = support.folder(self, "lh-inputs-")
        profile = support.write_json(
            os.path.join(inputs, "profile.json"), scratch.sample_profile(suite=recorded_suite(recorder, "suite"))
        )
        measured_profile = support.write_json(
            os.path.join(inputs, "measured-profile.json"),
            scratch.sample_profile(
                suite=recorded_suite(recorder, "measure-suite"),
                setup={"command": recorder.command("measure-setup")},
                start={"command": recorder.command("start"), "ready": "test -e " + recorder.record_path("start")},
            ),
        )
        record = support.record_with([support.exact_line("C1.1", recorder.command("check"))])
        self.assertEqual(support.referee_errors(support.H11, record), ())
        record_path = support.write_json(os.path.join(inputs, "record.json"), record)
        results = support.results_folder(self)
        exit_file = os.path.join(inputs, "never.exit")

        outcomes = [
            support.lighthouse(["worktrees", *build_flags(repo, results)], env, TYPED),
            support.lighthouse(["suite", *build_flags(repo, results), "--profile", profile], env, TYPED),
            support.lighthouse(["execute", "--results", results, "--record", record_path, "--profile", profile], env, TYPED),
            support.lighthouse(["profile", "measure", "--repo", repo, "--profile", measured_profile], env, TYPED),
            support.lighthouse(
                ["wait", "--until", recorder.command("wait") + " && true", "--exit-file", exit_file, "--every", "0.2"],
                env,
                TYPED,
            ),
        ]

        shown = "\n".join(stdout + stderr for _, stdout, stderr in outcomes)
        for name in ("suite", "check", "measure-setup", "start", "wait"):
            with self.subTest(record=name):
                self.assertTrue(os.path.exists(recorder.record_path(name)), "no {} record\n{}".format(name, shown))
                support.assert_noninteractive(self, recorder.read(name), name)

    def test_git_and_gh_get_no_input(self):
        repo, _ = support.feature_repo(self)
        stubs = support.Stubs(self)
        stubs.git_wrapper()
        env = support.environment(self, stubs.folder)

        code, stdout, stderr = support.lighthouse(
            ["change", "--repo", repo, "--core", "main", "--feature", "feature"], env, TYPED
        )

        git_calls = stubs.calls("git")
        gh_calls = stubs.calls("gh")
        shown = stdout + stderr
        self.assertGreaterEqual(len(git_calls), 1, shown)
        self.assertEqual(len(gh_calls), 1, shown)
        for index, call in enumerate(git_calls):
            support.assert_noninteractive(self, call, "git call {}".format(index))
        support.assert_noninteractive(self, gh_calls[0], "gh call")

    def test_with_credentials_and_child_get_no_input(self):
        repo, _ = support.feature_repo(self)
        home = scratch.make_home(self)
        profile = scratch.write_profile(repo, credentials_profile())
        write_credentials(home, repo)
        stubs = support.Stubs(self)
        recorder = support.Recorder(self)
        results = support.results_folder(self)
        line = support.blocked_line("stub reason")
        stubs.claude(results, [{"envelope": support.envelope(line, result=json.dumps(line))}])
        env = support.environment(self, stubs.folder, home=home)

        credentials_outcome = support.lighthouse(
            ["with-credentials", "--repo", repo, "--profile", profile, "--", *recorder.argv("with-credentials")],
            env,
            TYPED,
        )
        launch_outcome = support.lighthouse(["launch", *support.launch_flags(repo, results)], env, TYPED)

        shown = "\n".join(stdout + stderr for _, stdout, stderr in (credentials_outcome, launch_outcome))
        self.assertNotIn(CREDENTIAL_PASSWORD, shown)
        self.assertTrue(os.path.exists(recorder.record_path("with-credentials")), shown)
        support.assert_noninteractive(self, recorder.read("with-credentials"), "with-credentials")
        claude_calls = stubs.calls("claude")
        self.assertGreaterEqual(len(claude_calls), 1, shown)
        support.assert_noninteractive(self, claude_calls[0], "the child claude session")

    def test_existing_ssh_command_and_git_config_are_kept(self):
        repo, _ = support.feature_repo(self)
        stubs = support.Stubs(self)
        recorder = support.Recorder(self)
        env = support.environment(
            self,
            stubs.folder,
            extra={
                "GIT_SSH_COMMAND": "ssh -i /tmp/lighthouse-key",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.askPass",
                "GIT_CONFIG_VALUE_0": "true",
            },
        )
        profile = support.write_json(
            os.path.join(support.folder(self, "lh-inputs-"), "profile.json"),
            scratch.sample_profile(suite=recorded_suite(recorder, "suite", "core.askPass")),
        )
        results = support.results_folder(self)
        support.worktrees(self, repo, results, env)

        code, stdout, stderr = support.lighthouse(["suite", *build_flags(repo, results), "--profile", profile], env)

        self.assertTrue(os.path.exists(recorder.record_path("suite")), stdout + stderr)
        record = recorder.read("suite")
        ssh = record["env"]["GIT_SSH_COMMAND"] or ""
        self.assertTrue(ssh.startswith("ssh -i /tmp/lighthouse-key"), ssh)
        self.assertIn("-o BatchMode=yes", ssh)
        self.assertEqual(record["config"]["core.askPass"], "true", record)
        self.assertEqual(record["config"]["http.lowSpeedLimit"], "1", record)
        self.assertEqual(record["config"]["http.lowSpeedTime"], "60", record)


if __name__ == "__main__":
    unittest.main()
