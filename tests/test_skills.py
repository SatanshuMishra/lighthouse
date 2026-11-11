import json
import os
import re
import unittest

from tests import e2e_harness, scratch

SKILLS = ("init", "doctor", "test")
FOREGROUND_CALL = "in the foreground, as one Bash call with its timeout argument set to 604800000 and never with run_in_background"
LONG_LIGHTHOUSE_CALL = re.compile(r"[Rr]un `lighthouse (profile measure|suite|execute) ")
HOLDING_WAIT = re.compile(r"lighthouse wait --(ready|until) ")
LONG_TIMEOUT = "timeout argument set to 604800000"
SENTENCE_END = re.compile(r"(?<=[.:]) ")
FORBIDS_BACKGROUND = "never with run_in_background"
CALLER_STARTS = ("Start `lighthouse launch ", "In any other session, start `lighthouse profile measure ")
CHILD_BACKGROUND_START = "run_in_background and its timeout argument set to 604800000 as `("
SPLICED_PROFILE_TEXT = re.compile(r"curl -fsS <[^>]*>|grep -qF '<[^>]*>'|--until '<the ready check>'|'<the surface's sign_in command>'")


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


def driver_path():
    return os.path.join(scratch.ROOT, "agents", "driver.md")


def driver_text():
    return " ".join(scratch.read_text(driver_path()).replace("`", "").split())


def json_block(path):
    return scratch.read_text(path).split("```json", 1)[1].split("```", 1)[0]


def reference_line(reference, subcommand):
    prefix = "- `lighthouse {}`:".format(subcommand)
    return next(line for line in reference.splitlines() if line.startswith(prefix))


def parser_flags(arguments):
    return [option for action in arguments._actions for option in action.option_strings]


def instruction_files():
    skills = [scratch.skill_path(name) for name in sorted(os.listdir(os.path.join(scratch.ROOT, "skills")))]
    agents = os.path.join(scratch.ROOT, "agents")
    return [path for path in skills if os.path.isfile(path)] + [
        os.path.join(agents, name) for name in sorted(os.listdir(agents)) if name.endswith(".md")
    ]


def long_lighthouse_calls():
    return [
        (path, line)
        for path in instruction_files()
        for line in scratch.read_text(path).splitlines()
        if LONG_LIGHTHOUSE_CALL.search(line)
    ]


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
            "findings",
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
        self.assertIn("lighthouse verdict --blocked '<that reason>' --results <results>", text)
        reason = "the results folder must be outside the checkout"
        env = scratch.environment(scratch.make_home(self))
        code, stdout, stderr = scratch.run_lighthouse(["verdict", "--blocked", reason], env)
        self.assertEqual(code, 0, stderr)
        line = e2e_harness.last_json_line("{}\n{}".format(reason, stdout))
        self.assertEqual(
            line,
            {"verdict": "blocked", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "pr": None, "reason": reason},
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
        self.assertIn("lighthouse verdict --results <results>", steps)
        self.assertIn("lighthouse verdict --blocked '<that reason>' --results <results>", stopping)
        self.assertIn('"spend": {"tokens": <n>, "minutes": <n>, "dollars": <n or null>}', text)

    def test_test_skill_marks_every_path(self):
        text = scratch.skill_text("test")
        steps = section(text, "## Steps", "## Stopping early")

        self.assertIn(
            "Around each step below, run lighthouse mark --results <results> --step <name> start before it and the same with end after it",
            steps,
        )
        self.assertIn("naming the step worktrees, retest, profile, change, suite, execute, build, drive, spend, verdict, pr or release", steps)
        self.assertIn("mark the build step once per build with --build core or --build feature", steps)
        for step in ["worktrees", "retest", "profile", "change", "suite", "execute", "spend", "verdict", "pr", "release"]:
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
            "Start lighthouse launch <the flags you were given> --repo <repo> --parent <plugin>/<run> in the background, with run_in_background",
            launching,
        )
        self.assertIn("Wait for that command's completion notice, and run nothing else meanwhile", launching)
        self.assertIn("Once the notice arrives, read <results>/launch.json", launching)
        self.assertNotIn("lighthouse wait", launching)
        self.assertIn("Print the line in <results>/launch.json, unchanged, as the last line of the reply", launching)
        self.assertIn("With --child, run the Steps below", launching)
        self.assertNotIn("LIGHTHOUSE_CHILD", text)

    def test_a_blocked_launch_line_is_printed_with_its_reason_and_never_ledgered_twice(self):
        launching = section(scratch.skill_text("test"), "## Launch", "## Steps")
        self.assertIn("When that line's verdict is blocked, say in one line the reason lighthouse launch printed", launching)
        self.assertIn("lighthouse launch has already recorded the run in the metrics store, so never run Stopping early for it", launching)

    def test_test_skill_records_runs_in_the_store(self):
        text = scratch.skill_text("test")
        inputs = section(text, "## Inputs", "## Launch")
        launching = section(text, "## Launch", "## Steps")
        reference = scratch.read_text(scratch.skill_path("test")).split("## Command reference", 1)[1]
        stopping = section(text, "## Stopping early", "## Cost")

        self.assertIn("--parent <plugin>/<run>", inputs)
        self.assertIn("lighthouse launch <the flags you were given> --repo <repo> --parent <plugin>/<run>", launching)
        for command in re.findall(r"lighthouse verdict --[^,]*", text):
            with self.subTest(command=command):
                self.assertNotIn("--repo", command)
        self.assertNotIn("--repo", reference_line(reference, "verdict"))
        self.assertIn("--parent", reference_line(reference, "launch"))
        self.assertIn('"reason":', stopping)
        self.assertIn("metrics store", launching)
        self.assertNotIn("ledger", text)

    def test_test_skill_passes_only_a_parent_it_was_given(self):
        launching = section(scratch.skill_text("test"), "## Launch", "## Steps")
        self.assertIn("passing --parent only when you were given --parent", launching)

    def test_the_reference_names_the_blocked_reason(self):
        reference = scratch.read_text(scratch.skill_path("test")).split("## Command reference", 1)[1]
        for subcommand in ("launch", "verdict"):
            with self.subTest(subcommand=subcommand):
                self.assertIn("a blocked line has no `dollars` and adds `reason`", reference_line(reference, subcommand))

    def test_the_reference_says_a_blocked_line_has_no_dollars(self):
        reference = scratch.read_text(scratch.skill_path("test")).split("## Command reference", 1)[1]
        for subcommand in ("launch", "verdict"):
            with self.subTest(subcommand=subcommand):
                self.assertIn("a blocked line has no `dollars`", reference_line(reference, subcommand))

    def test_no_skill_splices_profile_text_into_a_shell_line(self):
        agents = os.path.join(scratch.ROOT, "agents")
        paths = [scratch.skill_path(name) for name in SKILLS] + [os.path.join(agents, name) for name in sorted(os.listdir(agents))]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(SPLICED_PROFILE_TEXT.findall(scratch.read_text(path)), [])

    def test_each_build_waits_and_signs_in_on_its_own_ports(self):
        text = scratch.skill_text("test")
        building = text.split("6. Build and start", 1)[1].split("7. Prove each path", 1)[0]
        for call in ("lighthouse wait --ready", "lighthouse with-credentials"):
            with self.subTest(call=call):
                line = next(line for line in building.splitlines() if call in line)
                self.assertIn("--port <profile port>=<build port>", line)

    def test_every_wait_instruction_names_the_exit_file_of_its_process(self):
        for path in (scratch.skill_path("test"), os.path.join(scratch.ROOT, "agents", "driver.md")):
            holds = [line for line in scratch.read_text(path).splitlines() if "lighthouse wait --" in line]
            with self.subTest(path=path):
                self.assertTrue(holds)
                for line in holds:
                    self.assertIn("--exit-file", line)
                    self.assertNotIn("ready false", line)

    def test_each_start_command_writes_its_pid_and_exit_file(self):
        text = scratch.skill_text("test")
        building = text.split("6. Build and start", 1)[1].split("7. Prove each path", 1)[0]

        self.assertIn(
            "starting it with run_in_background and its timeout argument set to 604800000 as (<start command>) > <results>/<build>-start.log 2>&1 < /dev/null & echo $! > <results>/<build>-start.pid; wait $!; echo $? > <results>/<build>-start.exit",
            building,
        )
        self.assertIn("--exit-file <results>/<build>-start.exit", building)
        self.assertIn("When that wait prints exited true with a status other than 0, the build did not start", building)
        self.assertIn("a profile problem for lighthouse:doctor, never a build that does not start", building)

    def test_release_stops_every_start_command_in_every_ending(self):
        text = scratch.skill_text("test")
        releasing = text.split("11. Run lighthouse release", 1)[1].split("12. When publish", 1)[0]
        stopping = section(text, "## Stopping early", "## Cost")

        self.assertIn("It also stops every start command the run started", releasing)
        self.assertIn(
            "whenever step 2 ran, run lighthouse release --repo <repo> --results <results>, so no started server keeps the session waiting",
            stopping,
        )
        self.assertLess(stopping.index("lighthouse release"), stopping.index("lighthouse verdict --blocked"))

    def test_the_child_holds_a_long_step_in_one_foreground_call_and_never_ends_a_turn_to_wait(self):
        text = scratch.skill_text("test")
        self.assertIn(
            "The child session holds every long step in the foreground instead: it runs the step as one Bash call with its timeout argument set to 604800000 and never with run_in_background",
            text,
        )
        self.assertIn("A child session never ends a turn while a command it started is still running", text)
        self.assertIn("A step that is still running is never a reason to stop early", text)
        self.assertIn("Run the wait itself in the foreground with its timeout argument set to 604800000", text)
        self.assertIn(
            "A process the child starts in the background gets that timeout too, because the Bash tool stops a background command when its timeout runs out",
            text,
        )
        self.assertIn(
            "Every other command keeps the Bash tool's own two-minute default, so one that hangs is moved to the background",
            text,
        )
        self.assertNotIn("When the Bash tool moves a foreground call to the background", text)
        self.assertIn(
            "Run each setup and build command in the foreground, as one Bash call with its timeout argument set to 604800000 and never with run_in_background",
            text,
        )
        driver = driver_text()
        self.assertIn("is moved to the background: stop such a command by its id, never by name or pattern", driver)
        self.assertIn("Run the wait in the foreground, as one Bash call with its timeout argument set to 604800000", driver)
        self.assertIn("Never end your turn while the wait or a command you started is still running", driver)
        self.assertNotIn("wait for its completion notice", driver)

    def test_every_hold_on_a_lighthouse_wait_asks_for_the_long_timeout(self):
        holds = [
            (path, line)
            for path in instruction_files()
            for line in scratch.read_text(path).splitlines()
            if HOLDING_WAIT.search(line)
        ]
        for holder in (scratch.skill_path("test"), driver_path()):
            with self.subTest(holder=holder):
                self.assertTrue(any(path == holder for path, _ in holds))
        for path, line in holds:
            with self.subTest(path=path, line=line[:80]):
                self.assertTrue(
                    any(
                        "wait" in sentence and "in the foreground" in sentence and LONG_TIMEOUT in sentence
                        for sentence in SENTENCE_END.split(line)
                    ),
                    "a wait here is held under the two-minute default",
                )

    def test_every_background_start_a_child_makes_asks_for_the_long_timeout(self):
        child_starts = [
            (path, sentence)
            for path in instruction_files()
            for line in scratch.read_text(path).splitlines()
            for sentence in SENTENCE_END.split(line)
            if "run_in_background" in sentence
            and FORBIDS_BACKGROUND not in sentence
            and not any(start in sentence for start in CALLER_STARTS)
        ]
        for starter in (scratch.skill_path("test"), driver_path()):
            with self.subTest(starter=starter):
                self.assertTrue(any(path == starter for path, _ in child_starts))
        for path, sentence in child_starts:
            with self.subTest(path=path, sentence=sentence[:80]):
                self.assertIn(
                    CHILD_BACKGROUND_START,
                    sentence,
                    "a process started here is stopped ten minutes after it starts",
                )

    def test_the_child_closes_stdin_of_every_command_it_runs(self):
        steps = section(scratch.skill_text("test"), "## Steps", "## Stopping early")

        self.assertIn("Start every command you run yourself with stdin from /dev/null", steps)

    def test_drivers_hold_only_on_a_named_exit_file(self):
        steps = section(scratch.skill_text("test"), "## Steps", "## Stopping early")
        driver = driver_text()

        self.assertIn("the exit file of each process the driver may hold on, such as <results>/<build>-start.exit", steps)
        self.assertIn("lighthouse wait --until '<check>' --exit-file <file>", driver)
        self.assertIn("(<command>) < /dev/null; echo $? > <file>", driver)
        self.assertIn("With neither, do not hold: return, naming what you would have waited for", driver)

    def test_cost_names_no_time_limit(self):
        cost = section(scratch.skill_text("test"), "## Cost", "## Never")

        self.assertNotIn("limit", cost)
        self.assertIn("a slow step runs to its end", cost)

    def test_test_skill_dispatches_drivers_in_the_foreground(self):
        steps = section(scratch.skill_text("test"), "## Steps", "## Stopping early")

        self.assertIn("Dispatch every driver through the lighthouse:driver agent in the foreground, never with run_in_background", steps)
        self.assertNotIn("a driver's result", steps)

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
            "Hold for a condition, such as a build, a server or a VM, only with lighthouse wait --until '<check>'",
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

    def test_skills_run_the_plugins_own_lighthouse(self):
        for name in SKILLS:
            text = scratch.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn(
                    "lighthouse in this skill always means ${CLAUDE_PLUGIN_ROOT}/bin/lighthouse: run it by that full path, written out in each command, never a lighthouse found on PATH, which may be an older installed copy",
                    text,
                )
                self.assertNotIn("when it is on PATH", text)

    def test_drivers_get_the_command_path(self):
        text = scratch.skill_text("test")
        driving = text.split("7. Prove each path by its check", 1)[1].split("8. Run lighthouse spend", 1)[0]
        driver = driver_text()
        given = driver.split("## What you are given", 1)[1].split("## Steps", 1)[0]

        self.assertIn(
            "Dispatch every driver through the lighthouse:driver agent, giving it the absolute path of the lighthouse command",
            driving,
        )
        self.assertIn("- The absolute path of the lighthouse command.", given)
        self.assertIn(
            "run lighthouse only by the absolute path you were given, written out in each command, never a lighthouse found on PATH",
            driver,
        )

    def test_skills_never_send_a_run_into_lighthouse_itself(self):
        texts = {**{name: scratch.skill_text(name) for name in SKILLS}, "driver": driver_text()}
        for name, text in texts.items():
            with self.subTest(file=name):
                self.assertIn("in what its commands print, including their refusals", text)
                self.assertIn("never read lighthouse's own code, profile schema or README, and never run its --help", text)
        for name in SKILLS:
            with self.subTest(skill=name):
                self.assertIn("Everything a run needs from lighthouse is in this skill and in what its commands print", texts[name])

    def test_test_skill_carries_a_command_reference(self):
        from lighthouse_tool import change, contrast, credentials, execute, findings, launch, mark, pr, profile, retest, spend, suite, verdict, wait

        raw = scratch.read_text(scratch.skill_path("test"))
        self.assertLess(raw.index("## Never"), raw.index("## Command reference"))
        reference = raw.split("## Command reference", 1)[1]
        parsers = {
            "launch": launch.parser(),
            "wait": wait.parser(),
            "mark": mark.parser(),
            "worktrees": suite.parser("worktrees"),
            "retest": retest.parser(),
            "profile check": profile.check_parser(),
            "profile publish": profile.publish_parser(),
            "profile measure": profile.measure_parser(),
            "execute": execute.parser(),
            "contrast": contrast.parser(),
            "change": change.parser(),
            "suite": suite.parser("suite"),
            "with-credentials": credentials.with_credentials_parser(),
            "spend": spend.parser(),
            "findings": findings.parser(),
            "verdict": verdict.parser(),
            "pr": pr.parser(),
            "release": suite.parser("release"),
        }
        for subcommand, arguments in parsers.items():
            line = reference_line(reference, subcommand)
            flags = parser_flags(arguments)
            with self.subTest(subcommand=subcommand):
                self.assertTrue(flags)
                for flag in flags:
                    self.assertRegex(line, re.escape("`" + flag) + r"[` ]")
        for flag in ["--until", "--every", "--exit-file"]:
            self.assertIn("`{} ".format(flag), reference_line(reference, "wait"))
        for retired in ["--within", "--limits", "expired", "limits.json"]:
            with self.subTest(retired=retired):
                self.assertNotIn(retired, reference_line(reference, "wait"))
                self.assertNotIn(retired, reference_line(reference, "launch"))
        keys = {
            "wait": ["ready", "exited", "status", "seconds"],
            "release": ["removed", "stopped"],
            "execute": ["checks", "neighbours"],
            "contrast": ["ratio", "threshold", "status", "source", "reason"],
            "profile measure": ["measured", "available"],
            "pr": ["title", "body", "base", "head", "draft", "error", "schema", "errors"],
            "findings": ["written", "error", "schema", "errors"],
            "retest": ["full", "changed", "retest", "surfaces", "carried"],
            "profile check": ["problems", "upgrades"],
            "profile publish": ["committed"],
            "spend": ["tokens", "minutes", "dollars"],
        }
        for subcommand, named in keys.items():
            line = reference_line(reference, subcommand)
            for key in named:
                with self.subTest(subcommand=subcommand, key=key):
                    self.assertIn("`{}`".format(key), line)
        text = scratch.skill_text("test")
        building = text.split("6. Build and start", 1)[1].split("7. Prove each path", 1)[0]
        self.assertIn("<results>/<build>-start.log", " ".join(reference.replace("`", "").split()))
        self.assertIn("Run each build's start command with its output written to <results>/<build>-start.log", building)
        self.assertIn("url for an http or https URL, ready once it answers with a status below 400", text)
        self.assertIn("line for a log line, ready once --log holds it", text)
        self.assertIn("command for a command, run as the profile writes it", text)
        self.assertIn("lighthouse wait --ready <url, line or command> --profile <results>/profile.json", building)

    def test_init_and_doctor_show_one_complete_example_profile(self):
        from lighthouse_tool import profile

        init_block = json_block(scratch.skill_path("init"))
        doctor_block = json_block(scratch.skill_path("doctor"))
        self.assertEqual(init_block, doctor_block)
        example = json.loads(init_block)
        self.assertEqual(profile.schema_problems(example, profile.load_schema()["profile"], "profile"), [])
        for field in ["setup", "build", "start", "test_data", "facts", "off_limits"]:
            self.assertIn(field, example)
        self.assertIn("rerun", example["suite"])
        self.assertIn("isolated", example["suite"])
        self.assertTrue(example["facts"])
        self.assertTrue(example["off_limits"])
        self.assertTrue(example["surfaces"])
        for key in ["name", "kind", "paths", "driver", "available", "sign_in", "credentials", "trials"]:
            self.assertIn(key, example["surfaces"][0])

    def test_marks_ride_in_the_commands_they_time(self):
        texts = {"test": section(scratch.skill_text("test"), "## Steps", "## Stopping early"), "driver": driver_text()}
        for name, text in texts.items():
            with self.subTest(file=name):
                self.assertIn("Run a start mark in the same Bash call as the first command it marks, joined by && or ;", text)
                self.assertIn("and the end mark in the same call as the last, always after ;", text)
                self.assertIn("never a mark in a Bash call of its own", text)
                self.assertIn("A mark around an action that is not a Bash call", text)
                self.assertIn("rides in the nearest Bash call before or after that action", text)

    def test_test_skill_names_paths_in_the_changes_words(self):
        text = scratch.skill_text("test")
        planning = text.split("5. Plan the paths.", 1)[1].split("6. Build and start", 1)[0]

        self.assertIn(
            "Name each path for the behaviour it checks in the words the spec, the merged pull requests and the commits use for it",
            planning,
        )
        self.assertIn("so the name under failures or unproven tells a reader what broke", planning)

    def test_every_long_lighthouse_call_runs_in_the_foreground_in_a_child_session(self):
        calls = long_lighthouse_calls()
        for name in SKILLS:
            with self.subTest(skill=name):
                self.assertTrue(any(path == scratch.skill_path(name) for path, _ in calls), name)
        for path, line in calls:
            for phrase in [FOREGROUND_CALL, "< /dev/null"]:
                with self.subTest(path=path, phrase=phrase, line=line[:80]):
                    self.assertIn(phrase, line)
            for retired in ["lighthouse wait", ".done", "600000"]:
                with self.subTest(path=path, retired=retired, line=line[:80]):
                    self.assertNotIn(retired, line)
            with self.subTest(path=path, line=line[:80]):
                self.assertEqual("completion notice" in line, path != scratch.skill_path("test"))

    def test_findings_reach_findings_json_only_through_lighthouse_findings(self):
        text = scratch.skill_text("test")
        writing = text.split("8. Run lighthouse spend", 1)[1].split("10. When the verdict", 1)[0]

        self.assertIn("9. Write the findings as the draft <results>/findings.draft.json:", writing)
        self.assertIn("Then run lighthouse findings --results <results>, marked as the verdict step", writing)
        self.assertIn("fix the draft by every error it names and run it again, until it exits 0", writing)
        self.assertIn("Never write <results>/findings.json yourself", writing)
        self.assertNotIn("Write <results>/findings.json", text)
        self.assertLess(writing.index("lighthouse findings --results"), writing.index("lighthouse verdict --results"))

        results = scratch.temporary_folder(self, "lighthouse-skill-findings-")
        draft = {
            "version": 1,
            "suite": {"result": "passed", "reason": None, "failures": [], "pre_existing": [], "flaky": [], "core": None, "feature": None},
            "build": {"result": "ok", "reason": None},
            "paths": [
                {
                    "name": "export writes a csv",
                    "kind": "new",
                    "surface": "cli",
                    "expected": "a csv with a header row",
                    "evidence": ["evidence/export.txt"],
                    "status": "skipped",
                    "retry": None,
                    "core": None,
                    "trials": None,
                    "check": {"kind": "direct", "why": "the command prints the outcome"},
                }
            ],
            "spend": {"tokens": 6000, "minutes": 2, "dollars": None},
        }
        with open(os.path.join(results, "findings.draft.json"), "w", encoding="utf-8") as handle:
            json.dump(draft, handle)
        env = scratch.environment(scratch.make_home(self))
        code, stdout, stderr = scratch.run_lighthouse(["findings", "--results", results], env)

        self.assertEqual(code, 2, stderr)
        printed = json.loads(stdout.strip().splitlines()[-1])
        self.assertEqual(sorted(printed), ["error", "errors", "schema"])
        self.assertEqual(printed["schema"], "h14-lighthouse-findings")
        self.assertTrue(any("/paths/0/status" in error for error in printed["errors"]))
        self.assertFalse(os.path.exists(os.path.join(results, "findings.json")))

    def test_test_skill_composes_the_pull_request_from_a_fields_draft(self):
        text = scratch.skill_text("test")
        opening = text.split("10. When the verdict", 1)[1].split("11. Run lighthouse release", 1)[0]

        self.assertIn("Write the pull request's prose as the fields draft <results>/pr-draft.json", opening)
        self.assertIn("each starting with a capital letter and ending with a full stop, with no markup, no links and no @", opening)
        self.assertIn("Name every failures, unproven and flaky name of the verdict line, exactly as the line spells it, in a tradeoffs sentence", opening)
        self.assertIn(
            "lighthouse pr --repo <repo> --core <core> --feature <feature> --results <results> --summary '<a lowercase summary of the feature>' --draft-fields <results>/pr-draft.json",
            opening,
        )
        self.assertIn("When it exits 2, it prints error, and schema and errors when the fields break their format: fix the draft by every error it names and run it again", opening)
        self.assertNotIn("--why", text)

    def test_the_skills_example_fields_draft_meets_h15(self):
        from lighthouse_tool import handoff, pr_fields

        raw = scratch.read_text(scratch.skill_path("test"))
        opening = raw.split("10. When the verdict", 1)[1].split("11. Run `lighthouse release", 1)[0]
        example = json.loads(opening.split("For example: `", 1)[1].split("`.", 1)[0])
        line = {"verdict": "unproven", "failures": [], "unproven": ["export of a large table"], "flaky": [], "tokens": 0, "minutes": 0, "dollars": None, "pr": None}
        findings = {"suite": {"result": "passed"}}
        title = pr_fields.compose_title("feat", "exports", "keep rows with an empty date")
        fields = pr_fields.build_fields(title, example, pr_fields.testing_rows(line, findings))

        self.assertEqual(sorted(example), ["change", "impact", "problem", "tradeoffs"])
        self.assertEqual(handoff.schema_errors("h15-pr-fields", fields), [])
        self.assertEqual(pr_fields.missing_names(line, fields), [])

    def test_test_skill_opens_the_pull_request_only_through_create_pull_request(self):
        text = scratch.skill_text("test")
        opening = text.split("10. When the verdict", 1)[1].split("11. Run lighthouse release", 1)[0]

        self.assertIn(
            "open the pull request only through the GitHub MCP create_pull_request tool, with the printed title, body, base and head unchanged, as a draft when draft is true and ready for review otherwise",
            opening,
        )
        self.assertIn("When this session has no create_pull_request tool, or the remote is not on GitHub, open nothing and say why in one line", opening)
        for path in instruction_files() + [os.path.join(scratch.ROOT, "README.md")]:
            with self.subTest(path=os.path.relpath(path, scratch.ROOT)):
                self.assertNotIn("gh pr create", " ".join(scratch.read_text(path).split()))

    def test_the_child_ends_with_its_verdict_line_as_structured_output(self):
        text = scratch.skill_text("test")
        ending = text.split("12. When publish exited non-zero", 1)[1].split("## Stopping early", 1)[0]
        stopping = text.split("## Stopping early", 1)[1].split("## Cost", 1)[0]

        self.assertIn("End the reply with the verdict line as structured output: set verdict_line to the line from <results>/verdict.json", ending)
        self.assertIn("pr, set to the pull request's URL or null", ending)
        self.assertIn("reads the reply only from that structured output, never from the reply's text", ending)
        self.assertIn("running lighthouse findings --results <results> and then lighthouse verdict --results <results> again", ending)
        self.assertIn("It asks once; a second failure blocks the run.", ending)
        self.assertNotIn("as the last line of the reply", ending)
        self.assertIn("end the reply with its line as structured output: set verdict_line to the blocked line it printed", stopping)
        self.assertNotIn("as the last line of the reply", stopping)

    def test_readme_describes_the_owned_hand_offs(self):
        readme = " ".join(scratch.read_text(os.path.join(scratch.ROOT, "README.md")).replace("`", "").split())

        for phrase in [
            "It writes its findings as <results>/findings.draft.json and runs lighthouse findings --results <results>",
            "| findings | --results <dir>:",
            "--draft-fields <file> the fields draft",
            "The child session hands its verdict line to lighthouse launch as structured output, never as text",
            "whose required verdict_line is h13-lighthouse-verdict-line's verdict or blocked form",
            "launch asks the same session once more with --resume and every error",
            "The child opens the pull request only through the GitHub MCP create_pull_request tool",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        self.assertNotIn("gh pr create", readme)


if __name__ == "__main__":
    unittest.main()
