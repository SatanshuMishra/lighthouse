import os
import shlex
import subprocess
import tempfile
import unittest

from lighthouse_tool import noninteractive

SSH_OPTIONS = "-o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4"
OWNER_SSH = shlex.quote(os.path.join(os.path.dirname(os.path.realpath(noninteractive.__file__)), "owner-ssh"))
UNREACHABLE_REMOTE = "ssh://git@example.invalid/x.git"
GIT_LIMIT_SECONDS = 60


class NoninteractiveEnvironment(unittest.TestCase):
    def test_values_on_an_empty_base(self):
        built = noninteractive.environment({"HOME": "/home/tester"})

        self.assertEqual(
            built,
            {
                "HOME": "/home/tester",
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "never",
                "GH_PROMPT_DISABLED": "1",
                "GIT_PAGER": "cat",
                "PAGER": "cat",
                "GIT_SSH_COMMAND": OWNER_SSH + " -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4",
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "http.lowSpeedLimit",
                "GIT_CONFIG_VALUE_0": "1",
                "GIT_CONFIG_KEY_1": "http.lowSpeedTime",
                "GIT_CONFIG_VALUE_1": "60",
            },
        )

    def test_interactive_values_in_the_base_are_replaced(self):
        built = noninteractive.environment(
            {"GIT_TERMINAL_PROMPT": "1", "GCM_INTERACTIVE": "always", "GH_PROMPT_DISABLED": "", "GIT_PAGER": "less", "PAGER": "more"}
        )

        self.assertEqual(built["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(built["GCM_INTERACTIVE"], "never")
        self.assertEqual(built["GH_PROMPT_DISABLED"], "1")
        self.assertEqual(built["GIT_PAGER"], "cat")
        self.assertEqual(built["PAGER"], "cat")

    def test_existing_ssh_command_is_extended(self):
        built = noninteractive.environment({"GIT_SSH_COMMAND": "ssh -i /tmp/lighthouse-key"})

        self.assertEqual(
            built["GIT_SSH_COMMAND"],
            "ssh -i /tmp/lighthouse-key -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4",
        )

    def test_blank_ssh_command_falls_back_to_the_owner_ssh(self):
        built = noninteractive.environment({"GIT_SSH_COMMAND": "  "})

        self.assertEqual(built["GIT_SSH_COMMAND"], OWNER_SSH + " " + SSH_OPTIONS)

    def test_existing_git_config_pairs_are_kept(self):
        built = noninteractive.environment(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.askPass",
                "GIT_CONFIG_VALUE_0": "true",
            }
        )

        self.assertEqual(built["GIT_CONFIG_COUNT"], "3")
        self.assertEqual(built["GIT_CONFIG_KEY_0"], "core.askPass")
        self.assertEqual(built["GIT_CONFIG_VALUE_0"], "true")
        self.assertEqual(built["GIT_CONFIG_KEY_1"], "http.lowSpeedLimit")
        self.assertEqual(built["GIT_CONFIG_VALUE_1"], "1")
        self.assertEqual(built["GIT_CONFIG_KEY_2"], "http.lowSpeedTime")
        self.assertEqual(built["GIT_CONFIG_VALUE_2"], "60")

    def test_base_is_left_unchanged(self):
        base = {
            "PATH": "/usr/bin",
            "GIT_SSH_COMMAND": "ssh -i /tmp/lighthouse-key",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.askPass",
            "GIT_CONFIG_VALUE_0": "true",
        }
        before = dict(base)

        built = noninteractive.environment(base)

        self.assertEqual(base, before)
        self.assertIsNot(built, base)

    def test_building_twice_adds_nothing_more(self):
        once = noninteractive.environment({"GIT_SSH_COMMAND": "ssh -i /tmp/lighthouse-key"})

        twice = noninteractive.environment(once)

        self.assertEqual(twice, once)
        self.assertEqual(twice["GIT_CONFIG_COUNT"], "2")

    def test_malformed_config_count_is_refused(self):
        with self.assertRaises(noninteractive.UnusableEnvironment) as raised:
            noninteractive.environment({"GIT_CONFIG_COUNT": "two"})

        self.assertIn("GIT_CONFIG_COUNT", str(raised.exception))



class OwnerSshIsKept(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="lh-owner-ssh-")
        self.addCleanup(self.work.cleanup)
        self.log = os.path.join(self.work.name, "calls.log")
        self.recorder = os.path.join(self.work.name, "user ssh")
        with open(self.recorder, "w") as handle:
            handle.write('#!/bin/sh\necho "$*" >> {}\nexit 1\n'.format(shlex.quote(self.log)))
        os.chmod(self.recorder, 0o755)
        self.home = os.path.join(self.work.name, "home")
        os.mkdir(self.home)
        self.repo = os.path.join(self.work.name, "repo")
        subprocess.run(["git", "init", "-q", self.repo], check=True, env=self.plain(), timeout=GIT_LIMIT_SECONDS)

    def plain(self):
        kept = {name: value for name, value in os.environ.items() if name not in ("GIT_SSH_COMMAND", "GIT_SSH") and not name.startswith("GIT_CONFIG")}
        return {**kept, "HOME": self.home, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}

    def ssh_calls(self, base):
        subprocess.run(
            ["git", "ls-remote", UNREACHABLE_REMOTE],
            cwd=self.repo,
            env=noninteractive.environment(base),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=GIT_LIMIT_SECONDS,
        )
        if not os.path.exists(self.log):
            return ""
        with open(self.log) as handle:
            return handle.read()

    def test_core_ssh_command_runs_with_batch_mode(self):
        subprocess.run(["git", "-C", self.repo, "config", "core.sshCommand", shlex.quote(self.recorder)], check=True, env=self.plain(), timeout=GIT_LIMIT_SECONDS)

        called = self.ssh_calls(self.plain())

        self.assertIn("-o BatchMode=yes", called)
        self.assertIn("git@example.invalid", called)

    def test_git_ssh_runs_with_batch_mode(self):
        called = self.ssh_calls({**self.plain(), "GIT_SSH": self.recorder})

        self.assertIn("-o BatchMode=yes", called)
        self.assertIn("git@example.invalid", called)


if __name__ == "__main__":
    unittest.main()
