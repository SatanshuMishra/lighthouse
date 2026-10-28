import os
import re
import unittest

from tests import scratch


def flattened(text):
    return " ".join(text.replace("`", "").split())


def raw_skill(name):
    return scratch.read_text(scratch.skill_path(name))


def driver_text():
    return flattened(scratch.read_text(os.path.join(scratch.ROOT, "agents", "driver.md")))


def section(text, heading, next_heading):
    return text.split(heading, 1)[1].split(next_heading, 1)[0]


def command_reference(raw):
    return raw.split("## Command reference", 1)[1]


def reference_lines(raw):
    return [line for line in command_reference(raw).splitlines() if line.startswith("- `lighthouse ")]


def sentences(text):
    return re.split(r"\.\s+", text)


def opens_as_draft_when_draft_is_true(sentence):
    without_phrase = sentence.replace("as a draft", "")
    return bool(
        re.search(r"\bas a draft\b", sentence)
        and re.search(r"\bdraft\b[^\n]*\btrue\b|\btrue\b[^\n]*\bdraft\b", without_phrase)
    )


class SkillExecutorTest(unittest.TestCase):
    def test_test_skill_executes_the_record(self):
        text = scratch.skill_text("test")

        for phrase in [
            "lighthouse execute --results <results>",
            "--record <record>",
            "plan.json",
            "Never write a findings path named for a check id.",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_command_reference_names_the_new_subcommands(self):
        lines = reference_lines(raw_skill("test"))

        for prefix in ["- `lighthouse execute`:", "- `lighthouse contrast`:", "- `lighthouse profile measure`:"]:
            with self.subTest(prefix=prefix):
                self.assertTrue(any(line.startswith(prefix) for line in lines), prefix)

    def test_launch_waits_within_the_run_limit(self):
        launching = section(scratch.skill_text("test"), "## Launch", "## Steps")

        self.assertIn("--limits <results>/limits.json", launching)
        self.assertRegex(launching, r"\bexpired\b")

    def test_driver_measures_contrast_with_the_command(self):
        text = driver_text()

        for phrase in ["lighthouse contrast", "--source declared", "--source tree", "--source pixels", "could-not-run"]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_init_and_doctor_measure_the_profile(self):
        for name in ["init", "doctor"]:
            with self.subTest(skill=name):
                self.assertIn("lighthouse profile measure --repo <repo>", scratch.skill_text(name))
        self.assertRegex(raw_skill("init"), r'[`"]reach[`"]')

    def test_test_skill_opens_the_pull_request_on_unproven(self):
        text = scratch.skill_text("test")

        self.assertIn("When the verdict is green or unproven, or --final is given", text)
        self.assertTrue(any(opens_as_draft_when_draft_is_true(sentence) for sentence in sentences(text)))


if __name__ == "__main__":
    unittest.main()
