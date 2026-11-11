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

    def test_init_and_doctor_keep_the_start_command_in_the_foreground(self):
        for name in ["init", "doctor"]:
            text = scratch.skill_text(name)

            self.assertIn(
                "The start command stays in the foreground until it is stopped, such as docker compose up and never docker compose up -d",
                text,
                name,
            )

    def test_init_and_doctor_run_measure_in_the_foreground_in_a_child_session_and_by_its_notice_elsewhere(self):
        for name in ["init", "doctor"]:
            text = scratch.skill_text(name)

            self.assertIn(
                "In a lighthouse:test child session, run lighthouse profile measure --repo <repo> > <folder>/measure.out 2>&1 < /dev/null in the foreground, as one Bash call with no timeout argument and never with run_in_background",
                text,
                name,
            )
            self.assertIn("never end the turn while it runs", text, name)
            self.assertIn(
                "In any other session, start lighthouse profile measure --repo <repo> > <folder>/measure.out 2>&1 < /dev/null with run_in_background, then wait for that command's completion notice",
                text,
                name,
            )
            for retired in ["measure.done", "lighthouse wait", "600000"]:
                self.assertNotIn(retired, text, name)

    def test_init_and_doctor_write_no_timeout_minutes(self):
        self.assertNotIn("timeout_minutes", scratch.skill_text("init"))
        for name in ["init", "doctor"]:
            example = scratch.read_text(scratch.skill_path(name)).split("```json", 1)[1].split("```", 1)[0]
            self.assertNotIn("timeout_minutes", example, name)

    def test_doctor_removes_the_retired_suite_timeout(self):
        text = scratch.skill_text("doctor")

        self.assertIn("retired: remove suite.timeout_minutes from the profile", text)


if __name__ == "__main__":
    unittest.main()
