import os
import re
import unittest

from tests import e2e_harness, scratch

SKILLS = ("init", "doctor", "test")


def frontmatter_name(text):
    found = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if found is None:
        return None
    named = re.search(r"(?m)^name:\s*(\S+)\s*$", found.group(1))
    return None if named is None else named.group(1)


class SkillsTest(unittest.TestCase):
    def test_ships_three_skills(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                self.assertTrue(os.path.isfile(scratch.skill_path(name)))
                self.assertEqual(frontmatter_name(scratch.read_text(scratch.skill_path(name))), name)

    def test_test_skill_states_its_contract(self):
        text = scratch.skill_text("test")

        for flag in ["--repo", "--core", "--feature", "--results", "--spec", "--final"]:
            self.assertIn(flag, text)
        for subcommand in [
            "worktrees",
            "profile check",
            "profile publish",
            "change",
            "suite",
            "with-credentials",
            "spend",
            "verdict",
            "pr",
            "release",
        ]:
            self.assertIn("lighthouse " + subcommand, text)
        for key in ["verdict", "failures", "unproven", "flaky", "tokens", "minutes", "pr"]:
            self.assertIn('"{}":'.format(key), text)

    def test_a_stop_before_the_verdict_still_ends_in_the_verdict_line(self):
        text = scratch.skill_text("test")
        self.assertIn("Every stop before step 9", text)
        self.assertIn("lighthouse verdict --blocked '<that reason>' --repo <repo> --results <results>", text)
        reason = "the results folder must be outside the checkout"
        env = scratch.environment(scratch.make_home(self))
        code, stdout, stderr = scratch.run_lighthouse(["verdict", "--blocked", reason], env)
        self.assertEqual(code, 0, stderr)
        line = e2e_harness.last_json_line("{}\n{}".format(reason, stdout))
        self.assertEqual(
            line,
            {"verdict": "blocked", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "pr": None},
        )


    def test_test_skill_retests_with_previous(self):
        text = scratch.skill_text("test")

        for phrase in [
            "--previous",
            "lighthouse retest",
            "a folder other than --results",
            "full is true",
            "carried_paths",
            "one-hop neighbours of the changed files",
            "replacing its copy",
            "exited non-zero",
            "plan every path as without --previous",
            "lighthouse suite on both builds",
        ]:
            self.assertIn(phrase, text)

    def test_test_skill_keeps_every_planned_retest_name(self):
        text = scratch.skill_text("test")
        planning = text.split("5. Plan the paths.", 1)[1].split("6. Build and start", 1)[0]
        writing = text.split("9. Write", 1)[1].split("10. When the verdict", 1)[0]

        for phrase in [
            "Every name in the plan's retest list is a planned path, whether full is true or not",
            "record it in findings.json under exactly that name",
            "never renamed, merged with another path or split into several",
            "add any fresh path beside them under a name of its own",
            "A carried path driven again keeps its name",
        ]:
            self.assertIn(phrase, planning)
        self.assertIn("It matches each name exactly", writing)

if __name__ == "__main__":
    unittest.main()
