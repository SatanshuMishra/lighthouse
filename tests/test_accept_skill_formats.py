import glob
import json
import os
import unittest

from tests import accept_support as support

BASE_VERSION = (0, 5, 0)
TEST_SKILL = os.path.join(support.ROOT, "skills", "test", "SKILL.md")


def holds(text, phrase):
    return phrase in text or phrase in support.collapsed(text)


def holds_prose(text, phrase):
    return phrase.lower() in support.collapsed(text).lower()


def shipped_texts():
    skills = sorted(glob.glob(os.path.join(support.ROOT, "skills", "*", "SKILL.md")))
    return [*skills, os.path.join(support.ROOT, "agents", "driver.md"), os.path.join(support.ROOT, "README.md")]


class SkillFormats(unittest.TestCase):
    def test_findings_go_through_lighthouse_findings(self):
        text = support.plain_text(TEST_SKILL)

        self.assertTrue(holds(text, "findings.draft.json"))
        self.assertTrue(holds(text, "lighthouse findings --results"))
        self.assertFalse(holds(text, "Write `<results>/findings.json`"))

    def test_no_gh_pr_create_fallback(self):
        for path in shipped_texts():
            with self.subTest(file=os.path.relpath(path, support.ROOT)):
                self.assertFalse(holds(support.plain_text(path), "gh pr create"))
        text = support.plain_text(TEST_SKILL)
        self.assertTrue(holds(text, "--draft-fields"))
        self.assertTrue(holds(text, "create_pull_request"))
        self.assertFalse(holds(text, "--why"))

    def test_child_ends_with_structured_output(self):
        text = support.plain_text(TEST_SKILL)

        self.assertTrue(holds_prose(text, "structured output"))
        self.assertTrue(holds(text, "verdict_line"))


class Release(unittest.TestCase):
    def test_version_rises_above_0_5_0_with_a_changelog_entry(self):
        manifest = support.read_json(os.path.join(support.ROOT, ".claude-plugin", "plugin.json"))
        version = manifest["version"]
        self.assertGreater(tuple(int(part) for part in version.split(".")), BASE_VERSION)

        code, stdout, stderr = support.lighthouse(["version"], support.environment(self))
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(json.loads(stdout.strip().splitlines()[-1]), {"version": version})

        changelog = os.path.join(support.ROOT, "CHANGELOG.md")
        self.assertTrue(os.path.isfile(changelog))
        lines = support.plain_text(changelog).splitlines()
        headings = [index for index, line in enumerate(lines) if line.startswith("## ")]
        self.assertTrue(headings, "CHANGELOG.md holds no ## heading")
        self.assertEqual(lines[headings[0]].strip(), "## " + version)
        end = headings[1] if len(headings) > 1 else len(lines)
        entry = "\n".join(lines[headings[0] : end])
        self.assertTrue(holds_prose(entry, "owned format"), entry)


if __name__ == "__main__":
    unittest.main()
