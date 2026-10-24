import os
import re
import unittest

from tests import e2e_harness, scratch

SKILLS = ("init", "doctor", "test")


def frontmatter_name(text):
    found = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if found is None:
        return None
    named = re.search(r"(?m)^name:\s*(\S+)\s*$", found.group(1))
    return None if named is None else named.group(1)


def frontmatter(text):
    found = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    return "" if found is None else found.group(1)


def section(text, heading, next_heading):
    return text.split(heading, 1)[1].split(next_heading, 1)[0]


class SkillsTest(unittest.TestCase):
    def test_ships_three_skills(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                self.assertTrue(os.path.isfile(scratch.skill_path(name)))
                self.assertEqual(frontmatter_name(scratch.read_text(scratch.skill_path(name))), name)

    def test_test_skill_states_its_contract(self):
        text = scratch.skill_text("test")

        for flag in ["--repo", "--core", "--feature", "--results", "--spec", "--final"]:
            self.assertIn(flag, text)
        for subcommand in [
            "worktrees",
            "profile check",
            "profile publish",
            "change",
            "suite",
            "with-credentials",
            "spend",
            "verdict",
            "pr",
            "release",
        ]:
            self.assertIn("lighthouse " + subcommand, text)
        for key in ["verdict", "failures", "unproven", "flaky", "tokens", "minutes", "pr"]:
            self.assertIn('"{}":'.format(key), text)

    def test_a_stop_before_the_verdict_still_ends_in_the_verdict_line(self):
        text = scratch.skill_text("test")
        self.assertIn("Every stop before step 9", text)
        self.assertIn("lighthouse verdict --blocked", text)
        reason = "the results folder must be outside the checkout"
        env = scratch.environment(scratch.make_home(self))
        code, stdout, stderr = scratch.run_lighthouse(["verdict", "--blocked", reason], env)
        self.assertEqual(code, 0, stderr)
        line = e2e_harness.last_json_line("{}\n{}".format(reason, stdout))
        self.assertEqual(
            line,
            {"verdict": "blocked", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "pr": None},
        )


    def test_test_skill_retests_with_previous(self):
        text = scratch.skill_text("test")

        for phrase in [
            "--previous",
            "lighthouse retest",
            "a folder other than --results",
            "full is true",
            "carried_paths",
            "one-hop neighbours of the changed files",
            "replacing its copy",
            "exited non-zero",
            "plan every path as without --previous",
            "reuses core's stored result",
        ]:
            self.assertIn(phrase, text)

    def test_test_skill_keeps_every_planned_retest_name(self):
        text = scratch.skill_text("test")
        planning = text.split("5. Plan the paths.", 1)[1].split("6. Build and start", 1)[0]
        writing = text.split("9. Write", 1)[1].split("10. When the verdict", 1)[0]

        for phrase in [
            "Every name in the plan's retest list is a planned path, whether full is true or not",
            "record it in findings.json under exactly that name",
            "never renamed, merged with another path or split into several",
            "add any fresh path beside them under a name of its own",
            "A carried path driven again keeps its name",
        ]:
            self.assertIn(phrase, planning)
        self.assertIn("It matches each name exactly", writing)

    def test_test_skill_records_spend_for_the_run(self):
        text = scratch.skill_text("test")
        steps = section(text, "## Steps", "## Stopping early")
        stopping = section(text, "## Stopping early", "## Cost")

        self.assertIn("lighthouse spend --since <start time> --results <results> --repo <repo>", steps)
        self.assertIn("keep its tokens, minutes and dollars", steps)
        self.assertIn("lighthouse verdict --results <results> --repo <repo>", steps)
        self.assertIn("lighthouse verdict --blocked '<that reason>' --repo <repo>", stopping)
        self.assertIn('"spend": {"tokens": <n>, "minutes": <n>, "dollars": <n or null>}', text)

    def test_test_skill_marks_every_path(self):
        text = scratch.skill_text("test")
        steps = section(text, "## Steps", "## Stopping early")

        self.assertIn(
            "Around each step below, run lighthouse mark --results <results> --step <name> start before it and the same with end after it",
            steps,
        )
        self.assertIn("naming the step worktrees, retest, profile, change, suite, build, drive, spend, verdict, pr or release", steps)
        self.assertIn("mark the build step once per build with --build core or --build feature", steps)
        for step in ["worktrees", "retest", "profile", "change", "suite", "spend", "verdict", "pr", "release"]:
            self.assertIn("marked as the {} step".format(step), steps)
        self.assertIn("each marked as the build step with its --build", steps)
        self.assertIn("all of it marked as the drive step", steps)
        self.assertIn(
            "Every driver, and you for a direct call, runs lighthouse mark --results <results> --step drive --build <core or feature> --path '<path name>' start before driving each path and the same with end after it",
            steps,
        )
        self.assertIn(
            "A driver that starts claude -p trial sessions for a path adds --folder <the folder they start in> to that path's start mark",
            steps,
        )

    def test_test_skill_reuses_core_suite(self):
        raw = scratch.read_text(scratch.skill_path("test"))
        text = scratch.skill_text("test")

        self.assertNotIn("Step 4 still runs `lighthouse suite` on both builds", raw)
        self.assertNotIn("Step 4 still runs lighthouse suite on both builds", text)
        self.assertIn(
            "lighthouse suite reuses core's stored result when core's commit and the profile's setup, build and suite commands match an earlier run",
            text,
        )
        self.assertIn("so a retest on an unmoved core never runs core's suite again, while FEATURE's suite always runs", text)

    def test_test_skill_runs_doctor_once_on_upgrades(self):
        text = scratch.skill_text("test")

        self.assertIn(
            "When the check passes and lists upgrades, invoke lighthouse:doctor --unattended --repo <results>/feature once for them and carry on whatever it does",
            text,
        )
        self.assertIn("upgrades never block the run and never stop it", text)

    def test_test_skill_launches_a_child_unless_inside_one(self):
        text = scratch.skill_text("test")
        launching = section(text, "## Launch", "## Steps")

        self.assertIn("--child: the flag lighthouse launch passes to the child session it starts; a person never passes it", text)
        self.assertIn("Without --child, do only this", launching)
        self.assertIn(
            "Start lighthouse launch <the flags you were given> --repo <repo> in the background, with run_in_background",
            launching,
        )
        self.assertIn("Run lighthouse wait --until 'test -s <results>/launch.json' in the foreground", launching)
        self.assertIn("Each time it returns with ready false, call it again, the same way, until it returns ready true", launching)
        self.assertIn("Print the line in <results>/launch.json, unchanged, as the last line of the reply", launching)
        self.assertIn("With --child, run the Steps below", launching)
        self.assertNotIn("LIGHTHOUSE_CHILD", text)

    def test_every_wait_instruction_sets_the_bash_timeout_to_its_ceiling(self):
        for path in (scratch.skill_path("test"), os.path.join(scratch.ROOT, "agents", "driver.md")):
            holds = [line for line in scratch.read_text(path).splitlines() if "lighthouse wait --until" in line]
            with self.subTest(path=path):
                self.assertTrue(holds)
                for line in holds:
                    self.assertIn("600000", line)

    def test_test_skill_dispatches_drivers_through_the_driver_agent(self):
        text = scratch.skill_text("test")
        steps = section(text, "## Steps", "## Stopping early")

        self.assertIn("Dispatch every driver through the lighthouse:driver agent", steps)
        self.assertIn("Every driver, and you for a direct call, runs lighthouse mark", steps)

    def test_driver_agent_uses_sonnet_and_a_one_hour_cache(self):
        text = scratch.read_text(os.path.join(scratch.ROOT, "agents", "driver.md"))
        header = frontmatter(text)

        self.assertEqual(frontmatter_name(text), "driver")
        self.assertRegex(header, r"(?m)^model:\s*sonnet\s*$")
        self.assertRegex(header, r"(?m)^experimental:\s*\n\s+cacheTtl:\s*1h\s*$")

    def test_test_skill_forbids_blind_sleeps_questions_and_narrowing(self):
        text = scratch.skill_text("test")

        self.assertIn(
            "Hold for a condition, such as a build, a server, a VM or a driver's result, only with lighthouse wait --until '<check>'",
            text,
        )
        self.assertIn("Never use a blind sleep", text)
        self.assertIn("Never hold with a blind sleep; hold only with lighthouse wait", text)
        self.assertIn("Never ask anything", text)
        self.assertIn("Never narrow scope to save time", text)
        self.assertIn(
            "An environment problem you cannot fix, such as a throttled VM or a sleeping host, leaves its paths unproven with that reason",
            text,
        )

    def test_test_skill_description_states_bypass_permissions(self):
        header = frontmatter(scratch.read_text(scratch.skill_path("test")))
        described = re.search(r"(?m)^description:\s*(.+)$", header)

        self.assertIsNotNone(described)
        self.assertIn("bypassPermissions", described.group(1))
        self.assertIn(
            "Use when a FEATURE branch holding merged changes must be proven before it merges into its core branch",
            described.group(1),
        )

    def test_test_skill_fits_each_check(self):
        text = scratch.skill_text("test")

        self.assertIn(
            "Choose each path's check: the lightest of suite, direct and drive that still observes the expected outcome on the surface the intent names",
            text,
        )
        self.assertIn(
            "suite: named tests in the project's suite assert the outcome and passed on FEATURE, and on core too for a neighbour",
            text,
        )
        self.assertIn("use it only when the suite writes a JUnit report", text)
        self.assertIn("direct: an HTTP or command-line call whose response holds the outcome", text)
        self.assertIn(
            "drive: the surface's recorded driver, when the outcome is what a person sees or which component a model chose",
            text,
        )
        self.assertIn("A new-behaviour path whose intent names something seen on screen uses drive", text)
        self.assertIn("Write its why naming the assertion or observation that shows the outcome", text)
        self.assertIn('"check": {"kind": "suite" or "direct" or "drive", "why": "...", "tests": ["..."]}', text)

    def test_test_skill_keeps_neighbours_and_trials(self):
        text = scratch.skill_text("test")

        self.assertIn("Go one hop only", text)
        self.assertIn("otherwise 3", text)

if __name__ == "__main__":
    unittest.main()
