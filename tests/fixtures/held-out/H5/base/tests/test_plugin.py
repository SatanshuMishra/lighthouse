import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
SCRIPTS = os.path.join(ROOT, "scripts")
SCRIPT_REFERENCE = re.compile(r"scripts/([A-Za-z_]+\.py)")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return None
    end = lines.index("---", 1)
    pairs = [line.split(":", 1) for line in lines[1:end] if ":" in line]
    return {key.strip(): value.strip() for key, value in pairs}


def skill_folders():
    return sorted(name for name in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, name)))


def script_names():
    return sorted(name for name in os.listdir(SCRIPTS) if name.endswith(".py"))


class PluginTest(unittest.TestCase):
    def test_manifest_names_the_plugin(self):
        manifest = json.loads(read(".claude-plugin", "plugin.json"))

        self.assertEqual(manifest["name"], "kilnmate")
        self.assertTrue(manifest["version"])

    def test_every_skill_has_valid_frontmatter(self):
        self.assertTrue(skill_folders())
        for name in skill_folders():
            with self.subTest(skill=name):
                fields = frontmatter(read("skills", name, "SKILL.md"))
                self.assertIsNotNone(fields)
                self.assertEqual(fields.get("name"), name)
                self.assertTrue(fields.get("description"))
                self.assertLessEqual(len(fields["description"]), 1024)

    def test_every_script_a_skill_names_exists(self):
        for name in skill_folders():
            for script in SCRIPT_REFERENCE.findall(read("skills", name, "SKILL.md")):
                with self.subTest(skill=name, script=script):
                    self.assertIn(script, script_names())

    def test_every_script_compiles(self):
        for script in script_names():
            with self.subTest(script=script):
                compile(read("scripts", script), script, "exec")

    def test_every_glaze_has_a_cone_and_segments(self):
        glazes = json.loads(read("data", "glazes.json"))["glazes"]
        self.assertTrue(glazes)
        for glaze in glazes:
            with self.subTest(glaze=glaze.get("name")):
                self.assertTrue(glaze["name"].strip())
                self.assertIsInstance(glaze["cone"], int)
                self.assertTrue(glaze["segments"])
                self.assertTrue(all(len(segment) == 3 for segment in glaze["segments"]))


if __name__ == "__main__":
    unittest.main()
