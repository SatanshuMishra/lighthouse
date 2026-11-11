import os
import re
import unittest

from tests import accept_support as support

TEST_SKILL = "skills/test/SKILL.md"
INIT_SKILL = "skills/init/SKILL.md"
DOCTOR_SKILL = "skills/doctor/SKILL.md"
DRIVER = "agents/driver.md"
README = "README.md"
LIMIT_WORDS = ("600000", "--within", "--limits", "limits.json", "`expired`", "expired true")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def text_of(relative):
    return support.plain_text(os.path.join(support.ROOT, relative))


def holds(text, phrase):
    return phrase in text or phrase in support.collapsed(text)


def holds_prose(text, phrase):
    return phrase.lower() in support.collapsed(text).lower()


def sentences(text):
    return [sentence for line in text.splitlines() for sentence in SENTENCE_END.split(line) if sentence.strip()]


class SkillText(unittest.TestCase):
    def test_no_skill_agent_or_readme_names_a_time_limit(self):
        for relative in (TEST_SKILL, INIT_SKILL, DOCTOR_SKILL, DRIVER, README):
            text = text_of(relative)
            for word in LIMIT_WORDS:
                with self.subTest(file=relative, word=word):
                    self.assertFalse(holds(text, word), "{} names {}".format(relative, word))
            if relative != DOCTOR_SKILL:
                with self.subTest(file=relative, word="timeout_minutes"):
                    self.assertFalse(holds(text, "timeout_minutes"), "{} names timeout_minutes".format(relative))

    def test_the_caller_holds_launch_by_its_completion_notice_and_waits_name_an_exit_file(self):
        test_skill = text_of(TEST_SKILL)
        init_skill = text_of(INIT_SKILL)
        doctor_skill = text_of(DOCTOR_SKILL)
        driver = text_of(DRIVER)
        cost = support.section(test_skill, "Cost")
        stopping = support.section(test_skill, "Stopping early")
        launching = support.section(test_skill, "Launch")

        self.assertNotIn("limit", cost)
        self.assertTrue(holds(launching, "run_in_background"))
        self.assertTrue(holds_prose(launching, "completion notice"))
        self.assertTrue(holds(test_skill, "--exit-file"))
        self.assertTrue(holds(driver, "--exit-file"))
        self.assertTrue(
            any("suite.timeout_minutes" in sentence and "remove" in sentence.lower() for sentence in sentences(doctor_skill)),
            "no doctor skill sentence removes suite.timeout_minutes",
        )
        self.assertTrue(holds_prose(doctor_skill, "completion notice"))
        self.assertFalse(holds(doctor_skill, "measure.done"))
        self.assertTrue(holds(stopping, "lighthouse release"))
        self.assertTrue(holds_prose(init_skill, "stays in the foreground"))
        self.assertTrue(holds_prose(doctor_skill, "stays in the foreground"))
        self.assertTrue(holds(driver, "start.exit"))


if __name__ == "__main__":
    unittest.main()
