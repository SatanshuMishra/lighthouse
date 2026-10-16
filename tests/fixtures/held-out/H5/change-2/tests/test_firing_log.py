import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class FiringLogTest(unittest.TestCase):
    def test_the_skill_pipes_the_json_schedule_into_the_log(self):
        skill = read("skills", "firing-log", "SKILL.md")

        self.assertIn("scripts/schedule.py\" --json", skill)
        self.assertIn("| python3", skill)
        self.assertIn("scripts/log_firing.py", skill)
        self.assertIn("Firing logged:", skill)

    def test_the_schedule_script_offers_json(self):
        script = read("scripts", "schedule.py")

        self.assertIn("--json", script)
        self.assertIn("json.dumps", script)

    def test_the_log_honours_kilnmate_log(self):
        self.assertIn("KILNMATE_LOG", read("scripts", "log_firing.py"))


if __name__ == "__main__":
    unittest.main()
