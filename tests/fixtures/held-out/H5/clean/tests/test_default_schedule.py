import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class DefaultScheduleTest(unittest.TestCase):
    def test_the_table_holds_a_cone_6_default(self):
        default = json.loads(read("data", "glazes.json"))["default"]

        self.assertEqual(default["cone"], 6)
        self.assertTrue(default["segments"])
        self.assertTrue(all(len(segment) == 3 for segment in default["segments"]))

    def test_the_skill_asks_for_a_test_tile_on_the_default(self):
        skill = read("skills", "firing-schedule", "SKILL.md")

        self.assertIn("default schedule", skill)
        self.assertIn("test fire a tile", skill)


if __name__ == "__main__":
    unittest.main()
