import unittest

from lighthouse_tool import noninteractive

SSH_OPTIONS = "-o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4"


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
                "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4",
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

    def test_blank_ssh_command_falls_back_to_ssh(self):
        built = noninteractive.environment({"GIT_SSH_COMMAND": "  "})

        self.assertEqual(built["GIT_SSH_COMMAND"], "ssh " + SSH_OPTIONS)

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


if __name__ == "__main__":
    unittest.main()
