import os
import re
import unittest

from tests import scratch


def skill_text(name):
    with open(os.path.join(scratch.ROOT, "skills", name, "SKILL.md"), encoding="utf-8") as handle:
        return " ".join(handle.read().replace("`", "").split())


class SkillInitDoctorTest(unittest.TestCase):
    def test_init_states_its_contract(self):
        text = skill_text("init")

        for named in ["--unattended", "lighthouse profile check", "lighthouse credentials init", "lighthouse answer"]:
            self.assertIn(named, text)
        self.assertRegex(text, re.compile(r"never ask[^.]*credential value", re.IGNORECASE))

    def test_doctor_states_its_contract(self):
        text = skill_text("doctor")

        for named in ["lighthouse profile check", "lighthouse credentials check", "lighthouse:init"]:
            self.assertIn(named, text)
        self.assertRegex(text, re.compile(r"change only \.lighthouse/profile\.json", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
