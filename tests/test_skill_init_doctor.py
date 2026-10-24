import re
import unittest

from tests import scratch


class SkillInitDoctorTest(unittest.TestCase):
    def test_init_states_its_contract(self):
        text = scratch.skill_text("init")

        for named in ["--unattended", "lighthouse profile check", "lighthouse credentials init", "lighthouse answer"]:
            self.assertIn(named, text)
        self.assertRegex(text, re.compile(r"never ask[^.]*credential value", re.IGNORECASE))

    def test_doctor_states_its_contract(self):
        text = scratch.skill_text("doctor")

        for named in ["lighthouse profile check", "lighthouse credentials check", "lighthouse:init"]:
            self.assertIn(named, text)
        self.assertRegex(text, re.compile(r"change only \.lighthouse/profile\.json", re.IGNORECASE))

    def test_init_and_doctor_fill_rerun_for_known_runners(self):
        for name in ["init", "doctor"]:
            text = scratch.skill_text(name)

            self.assertIn("suite.rerun", text, name)
            self.assertIn("python3 -m unittest {tests}", text, name)
            self.assertRegex(text, re.compile(r"pytest, suite\.command plus --lf"), name)
            self.assertRegex(text, re.compile(r"jest and vitest, suite\.command plus -t \{names_regex\}"), name)
            self.assertRegex(text, re.compile(r"go test, suite\.command plus -run \{names_regex\}"), name)
            self.assertIn("writing the same JUnit report as suite.command", text, name)
            self.assertIn("null for any runner without a way to select failures", text, name)

    def test_init_and_doctor_set_isolated_only_when_isolated(self):
        for name in ["init", "doctor"]:
            text = scratch.skill_text(name)

            self.assertRegex(
                text,
                re.compile(r"suite\.isolated: true only when the suite uses no fixed ports, shared databases or shared folders[^.]*; otherwise false"),
                name,
            )


if __name__ == "__main__":
    unittest.main()
