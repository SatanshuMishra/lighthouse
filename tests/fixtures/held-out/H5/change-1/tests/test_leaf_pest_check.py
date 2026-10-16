import os
import unittest

from tests.test_skills import SKILLS, frontmatter


class LeafPestCheckTest(unittest.TestCase):
    def test_the_skill_is_described_by_its_symptoms(self):
        fields = frontmatter(os.path.join(SKILLS, "leaf-pest-check", "SKILL.md"))

        self.assertEqual(fields["name"], "leaf-pest-check")
        self.assertIn("pest", fields["description"])


if __name__ == "__main__":
    unittest.main()
