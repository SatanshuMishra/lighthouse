import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")


def frontmatter(path):
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return None
    end = lines.index("---", 1)
    pairs = [line.split(":", 1) for line in lines[1:end] if ":" in line]
    return {key.strip(): value.strip() for key, value in pairs}


def skill_folders():
    return sorted(name for name in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, name)))


class SkillsTest(unittest.TestCase):
    def test_manifest_names_the_plugin(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)

        self.assertEqual(manifest["name"], "greenhand")
        self.assertTrue(manifest["version"])

    def test_every_skill_has_valid_frontmatter(self):
        self.assertTrue(skill_folders())
        for name in skill_folders():
            with self.subTest(skill=name):
                fields = frontmatter(os.path.join(SKILLS, name, "SKILL.md"))
                self.assertIsNotNone(fields)
                self.assertEqual(fields.get("name"), name)
                self.assertTrue(fields.get("description"))
                self.assertLessEqual(len(fields["description"]), 1024)


if __name__ == "__main__":
    unittest.main()
