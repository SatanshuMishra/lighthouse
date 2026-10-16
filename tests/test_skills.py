import os
import re
import unittest

from tests import scratch

SKILLS = ("init", "doctor", "test")


def skill_path(name):
    return os.path.join(scratch.ROOT, "skills", name, "SKILL.md")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def frontmatter_name(text):
    found = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if found is None:
        return None
    named = re.search(r"(?m)^name:\s*(\S+)\s*$", found.group(1))
    return None if named is None else named.group(1)


def skill_text(name):
    return " ".join(read_text(skill_path(name)).replace("`", "").split())


class SkillsTest(unittest.TestCase):
    def test_ships_three_skills(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                self.assertTrue(os.path.isfile(skill_path(name)))
                self.assertEqual(frontmatter_name(read_text(skill_path(name))), name)

    def test_test_skill_states_its_contract(self):
        text = skill_text("test")

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


if __name__ == "__main__":
    unittest.main()
