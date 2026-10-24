import json
import os
import re
import unittest

from tests import scratch


def assistant(identifier, timestamp, usage, model="claude-opus-5-5", cwd=None, content=None, stop_reason=None):
    entry = {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {"id": identifier, "model": model, "usage": usage, "content": content or [], "stop_reason": stop_reason},
    }
    return json.dumps({**entry, "cwd": cwd} if cwd else entry)


def tool_result(tool_use_id, timestamp, cwd=None):
    entry = {
        "type": "user",
        "timestamp": timestamp,
        "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": "done"}]},
    }
    return json.dumps({**entry, "cwd": cwd} if cwd else entry)


def tool_use(tool_use_id, name, tool_input):
    return [{"type": "tool_use", "id": tool_use_id, "name": name, "input": tool_input}]


def bash(tool_use_id, command):
    return tool_use(tool_use_id, "Bash", {"command": command})


def write_transcript(folder, relative_path, lines):
    path = os.path.join(folder, relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def project_name(path):
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def write_session(home, cwd, relative_path, lines):
    folder = os.path.join(home, ".claude", "projects", project_name(cwd))
    return write_transcript(folder, relative_path, lines)


def spend_of(test, arguments, home=None):
    env = scratch.environment(home or scratch.make_home(test))
    code, stdout, stderr = scratch.run_lighthouse(["spend", "--since", "2026-10-16T09:00:00Z", *arguments], env)
    test.assertEqual(code, 0, stderr)
    return json.loads(stdout.strip().splitlines()[-1])


def spend_of_lines(test, lines, extra=()):
    transcripts = scratch.temporary_folder(test, "lh-transcripts-")
    write_transcript(transcripts, "session.jsonl", lines)
    return spend_of(test, ["--transcripts", transcripts, *extra])


def path_named(spend, name):
    return next(path for path in spend["paths"] if path["name"] == name)


def step_named(spend, name):
    return next(step for step in spend["steps"] if step["name"] == name)


def write_marks(results, folder, start, end):
    lines = [
        {"step": "drive", "build": "feature", "path": "pick skill", "folder": folder, "edge": edge, "time": time}
        for edge, time in (("start", start), ("end", end))
    ]
    with open(os.path.join(results, "marks.jsonl"), "w", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(line) + "\n" for line in lines))


class SpendTest(unittest.TestCase):
    def test_sums_tokens_once_per_message(self):
        transcripts = scratch.temporary_folder(self, "lh-transcripts-")
        repeated = assistant(
            "msg_shared",
            "2026-10-16T10:05:00.000Z",
            {"input_tokens": 10, "cache_creation_input_tokens": 20, "cache_read_input_tokens": 300, "output_tokens": 40},
        )
        write_transcript(
            transcripts,
            "session.jsonl",
            [
                assistant(
                    "msg_before",
                    "2026-10-16T09:59:00.000Z",
                    {"input_tokens": 1000, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 1000, "output_tokens": 1000},
                ),
                "not json",
                json.dumps({"type": "user", "timestamp": "2026-10-16T10:01:00.000Z", "message": {"content": "hi"}}),
                repeated,
                assistant("msg_main", "2026-10-16T10:02:00.000Z", {"cache_read_input_tokens": 500, "output_tokens": 60}),
            ],
        )
        write_transcript(
            transcripts,
            os.path.join("session", "subagents", "agent-1.jsonl"),
            [
                repeated,
                assistant(
                    "msg_subagent",
                    "2026-10-16T10:12:30.000Z",
                    {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 200, "output_tokens": 25},
                ),
            ],
        )
        env = scratch.environment(scratch.make_home(self))

        code, stdout, stderr = scratch.run_lighthouse(
            ["spend", "--since", "2026-10-16T10:00:00Z", "--transcripts", transcripts], env
        )

        self.assertEqual(code, 0, stderr)
        spend = json.loads(stdout.strip().splitlines()[-1])
        self.assertEqual(
            {key: spend[key] for key in ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output", "tokens", "messages", "minutes")},
            {
                "input": 15,
                "cache_write_5m": 20,
                "cache_write_1h": 0,
                "cache_read": 1000,
                "output": 125,
                "tokens": 1160,
                "messages": 3,
                "minutes": 12.5,
            },
        )

    def test_from_names_the_project_folder(self):
        home = scratch.make_home(self)
        write_transcript(
            home,
            os.path.join(".claude", "projects", "-tmp-work", "s.jsonl"),
            [assistant("msg_only", "2026-10-16T10:03:00Z", {"cache_read_input_tokens": 100, "output_tokens": 7})],
        )
        env = scratch.environment(home)

        code, stdout, stderr = scratch.run_lighthouse(
            ["spend", "--since", "2026-10-16T10:00:00Z", "--from", "/tmp/work"], env
        )

        self.assertEqual(code, 0, stderr)
        spend = json.loads(stdout.strip().splitlines()[-1])
        self.assertEqual(spend["messages"], 1)

    def test_spend_splits_cache_writes_by_lifetime(self):
        spend = spend_of_lines(
            self,
            [
                assistant(
                    "msg_split",
                    "2026-10-16T10:00:00Z",
                    {
                        "cache_creation_input_tokens": 400,
                        "cache_creation": {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 300},
                    },
                )
            ],
        )
        self.assertEqual(spend["cache_write_5m"], 100)
        self.assertEqual(spend["cache_write_1h"], 300)

    def test_spend_counts_an_unsplit_cache_write_as_five_minute(self):
        spend = spend_of_lines(self, [assistant("msg_unsplit", "2026-10-16T10:00:00Z", {"cache_creation_input_tokens": 250})])
        self.assertEqual(spend["cache_write_5m"], 250)
        self.assertEqual(spend["cache_write_1h"], 0)

    def test_spend_prices_each_model(self):
        prices = os.path.join(scratch.temporary_folder(self, "lh-prices-"), "prices.json")
        with open(prices, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"claude-sonnet-5-5": {"input": 2.0, "cache_write_5m": 2.5, "cache_write_1h": 4.0, "cache_read": 0.2, "output": 10.0}}
                )
            )
        spend = spend_of_lines(
            self,
            [assistant("msg_sonnet", "2026-10-16T10:00:00Z", {"input_tokens": 1000000}, model="claude-sonnet-5-5")],
            ["--prices", prices],
        )
        self.assertEqual(spend["models"]["claude-sonnet-5-5"]["dollars"], 2.0)
        self.assertEqual(spend["dollars"], 2.0)

    def test_unknown_model_has_null_dollars(self):
        spend = spend_of_lines(
            self, [assistant("msg_unknown", "2026-10-16T10:00:00Z", {"output_tokens": 10}, model="claude-imaginary-9")]
        )
        self.assertIsNone(spend["dollars"])
        self.assertIn("claude-imaginary-9", spend["unpriced"])

    def test_tokens_total_is_the_sum_of_every_kind(self):
        spend = spend_of_lines(
            self,
            [
                assistant("msg_fresh", "2026-10-16T10:00:00Z", {"input_tokens": 10, "cache_read_input_tokens": 40}),
                assistant(
                    "msg_written",
                    "2026-10-16T10:01:00Z",
                    {
                        "cache_creation": {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 30},
                        "output_tokens": 50,
                    },
                ),
            ],
        )
        self.assertEqual(spend["tokens"], 150)

    def test_a_zero_token_unknown_model_is_not_unpriced(self):
        spend = spend_of_lines(
            self,
            [
                assistant("msg_priced", "2026-10-16T10:00:00Z", {"output_tokens": 1000}, model="claude-opus-5-5"),
                assistant(
                    "msg_synthetic",
                    "2026-10-16T10:01:00Z",
                    {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0},
                    model="<synthetic>",
                ),
            ],
        )
        self.assertEqual(spend["dollars"], spend["models"]["claude-opus-5-5"]["dollars"])
        self.assertEqual(spend["dollars"], 0.02)
        self.assertEqual(spend["unpriced"], [])

    def test_spend_counts_sessions_started_under_results(self):
        home = scratch.make_home(self)
        results = scratch.temporary_folder(self, "lh-results-")
        work = os.path.join(results, "work")
        trial = os.path.join(work, "core-trial")
        write_session(home, work, "child.jsonl", [assistant("msg_child", "2026-10-16T10:00:00Z", {"output_tokens": 11}, cwd=work)])
        write_session(home, trial, "trial.jsonl", [assistant("msg_trial", "2026-10-16T10:01:00Z", {"output_tokens": 13}, cwd=trial)])
        spend = spend_of(self, ["--results", results], home)
        self.assertEqual(spend["messages"], 2)
        self.assertEqual(spend["output"], 24)

    def test_spend_counts_subagent_transcripts(self):
        home = scratch.make_home(self)
        results = scratch.temporary_folder(self, "lh-results-")
        work = os.path.join(results, "work")
        write_session(home, work, "session.jsonl", [assistant("msg_child", "2026-10-16T10:00:00Z", {"output_tokens": 11}, cwd=work)])
        write_session(
            home,
            work,
            os.path.join("session", "subagents", "agent-1.jsonl"),
            [assistant("msg_driver", "2026-10-16T10:01:00Z", {"output_tokens": 17}, cwd=work)],
        )
        spend = spend_of(self, ["--results", results], home)
        self.assertEqual(spend["messages"], 2)
        self.assertEqual(spend["output"], 28)

    def test_spend_ignores_a_colliding_folder_outside_results(self):
        home = scratch.make_home(self)
        parent = scratch.temporary_folder(self, "lh-runs-")
        results = os.path.join(parent, "run.1")
        sibling = os.path.join(parent, "run-1")
        os.makedirs(results)
        os.makedirs(sibling)
        self.assertEqual(project_name(results), project_name(sibling))
        write_session(home, results, "ours.jsonl", [assistant("msg_ours", "2026-10-16T10:00:00Z", {"output_tokens": 5}, cwd=results)])
        write_session(home, sibling, "theirs.jsonl", [assistant("msg_theirs", "2026-10-16T10:01:00Z", {"output_tokens": 700}, cwd=sibling)])
        spend = spend_of(self, ["--results", results], home)
        self.assertEqual(spend["messages"], 1)
        self.assertEqual(spend["output"], 5)

    def test_spend_counts_a_rewrite_after_a_five_minute_gap(self):
        spend = spend_of_lines(
            self,
            [
                assistant("msg_first", "2026-10-16T10:00:00Z", {"output_tokens": 10}),
                assistant(
                    "msg_rewrite",
                    "2026-10-16T10:06:00Z",
                    {"cache_creation_input_tokens": 200000, "cache_creation": {"ephemeral_5m_input_tokens": 200000, "ephemeral_1h_input_tokens": 0}},
                ),
            ],
        )
        self.assertEqual(spend["expired_rewrites"], {"count": 1, "tokens": 200000})

    def test_a_one_hour_cache_survives_a_ten_minute_gap(self):
        one_hour_write = {"cache_creation_input_tokens": 5000, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 5000}}
        spend = spend_of_lines(
            self,
            [
                assistant("msg_first", "2026-10-16T10:00:00Z", one_hour_write),
                assistant("msg_second", "2026-10-16T10:10:00Z", one_hour_write),
            ],
        )
        self.assertEqual(spend["expired_rewrites"]["count"], 0)

    def test_a_one_hour_transcript_turn_after_a_quiet_message_is_not_expired(self):
        one_hour_write = {"cache_creation_input_tokens": 5000, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 5000}}
        spend = spend_of_lines(
            self,
            [
                assistant("msg_first", "2026-10-16T10:00:00Z", one_hour_write),
                assistant("msg_quiet", "2026-10-16T10:01:00Z", {"cache_read_input_tokens": 5000, "output_tokens": 3}),
                assistant("msg_third", "2026-10-16T10:11:00Z", one_hour_write),
            ],
        )
        self.assertEqual(spend["expired_rewrites"]["count"], 0)

    def test_answer_wait_counts_as_waiting_on_a_person(self):
        spend = spend_of_lines(
            self,
            [
                assistant(
                    "msg_ask",
                    "2026-10-16T10:00:00Z",
                    {"output_tokens": 30},
                    content=tool_use("toolu_ask", "AskUserQuestion", {"questions": []}),
                    stop_reason="tool_use",
                ),
                tool_result("toolu_ask", "2026-10-16T12:00:00Z"),
            ],
        )
        self.assertEqual(spend["waiting"]["person"], 120)
        self.assertEqual(spend["waiting"]["tool"], 0)

    def test_tool_wait_counts_as_tool_minutes(self):
        spend = spend_of_lines(
            self,
            [
                assistant(
                    "msg_bash",
                    "2026-10-16T10:00:00Z",
                    {"output_tokens": 30},
                    content=bash("toolu_bash", "make test"),
                    stop_reason="tool_use",
                ),
                tool_result("toolu_bash", "2026-10-16T10:30:00Z"),
            ],
        )
        self.assertEqual(spend["waiting"]["tool"], 30)
        self.assertEqual(spend["waiting"]["person"], 0)

    def test_spend_attributes_turns_between_marks_to_the_path(self):
        start = "lighthouse mark --results /tmp/r --step drive --build feature --path 'sign in' start"
        end = "lighthouse mark --results /tmp/r --step drive --build feature --path 'sign in' end"
        spend = spend_of_lines(
            self,
            [
                assistant("msg_start", "2026-10-16T10:00:00Z", {"cache_read_input_tokens": 10}, content=bash("toolu_start", start)),
                tool_result("toolu_start", "2026-10-16T10:00:01Z"),
                assistant("msg_one", "2026-10-16T10:01:00Z", {"output_tokens": 100}),
                assistant("msg_two", "2026-10-16T10:02:00Z", {"output_tokens": 100}),
                assistant("msg_end", "2026-10-16T10:03:00Z", {"cache_read_input_tokens": 10}, content=bash("toolu_end", end)),
                tool_result("toolu_end", "2026-10-16T10:03:01Z"),
            ],
        )
        self.assertEqual(path_named(spend, "sign in")["output"], 200)

    def test_turns_outside_marks_are_shared(self):
        start = "lighthouse mark --results /tmp/r --step drive --path 'sign in' start"
        end = "lighthouse mark --results /tmp/r --step drive --path 'sign in' end"
        spend = spend_of_lines(
            self,
            [
                assistant("msg_before", "2026-10-16T09:59:00Z", {"output_tokens": 50}),
                assistant("msg_start", "2026-10-16T10:00:00Z", {"cache_read_input_tokens": 10}, content=bash("toolu_start", start)),
                tool_result("toolu_start", "2026-10-16T10:00:01Z"),
                assistant("msg_end", "2026-10-16T10:01:00Z", {"cache_read_input_tokens": 10}, content=bash("toolu_end", end)),
                tool_result("toolu_end", "2026-10-16T10:01:01Z"),
            ],
        )
        self.assertEqual(spend["shared"]["output"], 50)
        self.assertTrue(all(path["output"] == 0 for path in spend["paths"]))

    def test_a_trial_session_in_a_marked_folder_belongs_to_its_path(self):
        home = scratch.make_home(self)
        results = scratch.temporary_folder(self, "lh-results-")
        work = os.path.join(results, "work")
        trials = os.path.join(work, "trials", "pick-skill")
        trial = os.path.join(trials, "feature", "1")
        marked = "lighthouse mark --results {} --step drive --build feature --path 'pick skill' --folder {} ".format(results, trials)
        write_session(
            home,
            work,
            "child.jsonl",
            [
                assistant("msg_start", "2026-10-16T10:00:00Z", {"cache_read_input_tokens": 10}, cwd=work, content=bash("toolu_start", marked + "start")),
                tool_result("toolu_start", "2026-10-16T10:00:01Z", cwd=work),
                assistant("msg_end", "2026-10-16T10:05:00Z", {"cache_read_input_tokens": 10}, cwd=work, content=bash("toolu_end", marked + "end")),
                tool_result("toolu_end", "2026-10-16T10:05:01Z", cwd=work),
            ],
        )
        write_session(home, trial, "trial.jsonl", [assistant("msg_trial", "2026-10-16T10:02:00Z", {"output_tokens": 300}, cwd=trial)])
        write_marks(results, trials, "2026-10-16T10:00:00.400Z", "2026-10-16T10:05:00.400Z")
        spend = spend_of(self, ["--results", results], home)
        self.assertEqual(path_named(spend, "pick skill")["output"], 300)

    def test_a_folder_marked_after_cd_belongs_to_its_path(self):
        home = scratch.make_home(self)
        results = scratch.temporary_folder(self, "lh-results-")
        work = os.path.join(results, "work")
        trials = os.path.join(work, "trials")
        folder = os.path.join(trials, "pick-skill")
        trial = os.path.join(folder, "feature", "1")
        decoy = os.path.join(work, "other", "1")
        marked = "cd {} && lighthouse mark --results {} --step drive --build feature --path 'pick skill' --folder pick-skill ".format(
            trials, results
        )
        write_session(
            home,
            work,
            "child.jsonl",
            [
                assistant("msg_start", "2026-10-16T10:00:00Z", {"cache_read_input_tokens": 10}, cwd=work, content=bash("toolu_start", marked + "start")),
                tool_result("toolu_start", "2026-10-16T10:00:01Z", cwd=work),
                assistant("msg_end", "2026-10-16T10:05:00Z", {"cache_read_input_tokens": 10}, cwd=work, content=bash("toolu_end", marked + "end")),
                tool_result("toolu_end", "2026-10-16T10:05:01Z", cwd=work),
            ],
        )
        write_session(home, trial, "trial.jsonl", [assistant("msg_trial", "2026-10-16T10:02:00Z", {"output_tokens": 300}, cwd=trial)])
        write_session(home, decoy, "decoy.jsonl", [assistant("msg_decoy", "2026-10-16T10:03:00Z", {"output_tokens": 50}, cwd=decoy)])
        write_marks(results, folder, "2026-10-16T10:00:00.400Z", "2026-10-16T10:05:00.400Z")
        spend = spend_of(self, ["--results", results], home)
        self.assertEqual(path_named(spend, "pick skill")["output"], 300)

    def test_a_mark_chained_into_its_command_owns_that_message(self):
        home = scratch.make_home(self)
        results = scratch.temporary_folder(self, "lh-results-")
        work = os.path.join(results, "work")
        chained = "lighthouse mark --results {0} --step suite start && lighthouse suite --repo X; lighthouse mark --results {0} --step suite end".format(
            results
        )
        write_session(
            home,
            work,
            "child.jsonl",
            [
                assistant("msg_suite", "2026-10-16T09:59:58Z", {"output_tokens": 100}, cwd=work, content=bash("toolu_suite", chained)),
                tool_result("toolu_suite", "2026-10-16T10:01:31Z", cwd=work),
            ],
        )
        lines = [
            {"step": "suite", "build": None, "path": None, "folder": None, "edge": "start", "time": "2026-10-16T10:00:00Z"},
            {"step": "suite", "build": None, "path": None, "folder": None, "edge": "end", "time": "2026-10-16T10:01:30Z"},
        ]
        with open(os.path.join(results, "marks.jsonl"), "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(line) + "\n" for line in lines))
        spend = spend_of(self, ["--results", results], home)
        self.assertEqual(step_named(spend, "suite")["output"], 100)
        self.assertEqual(step_named(spend, "suite")["minutes"], 1.5)
        self.assertEqual(spend["shared"]["tokens"], 0)

    def test_a_mark_through_a_shell_variable_counts(self):
        start = "LH=/x/bin/lighthouse; $LH mark --results R --step drive --build feature --path 'sign in' start"
        end = "LH=/x/bin/lighthouse; $LH mark --results R --step drive --build feature --path 'sign in' end"
        spend = spend_of_lines(
            self,
            [
                assistant("msg_start", "2026-10-16T10:00:00Z", {"cache_read_input_tokens": 10}, content=bash("toolu_start", start)),
                tool_result("toolu_start", "2026-10-16T10:00:01Z"),
                assistant("msg_one", "2026-10-16T10:01:00Z", {"output_tokens": 100}),
                assistant("msg_end", "2026-10-16T10:02:00Z", {"cache_read_input_tokens": 10}, content=bash("toolu_end", end)),
                tool_result("toolu_end", "2026-10-16T10:02:01Z"),
            ],
        )
        self.assertEqual(path_named(spend, "sign in")["output"], 100)

    def test_a_mark_on_a_later_row_of_its_message_owns_that_message(self):
        chained = "lighthouse mark --results R --step suite start && lighthouse suite --repo X; lighthouse mark --results R --step suite end"
        thinking = [{"type": "thinking", "thinking": "run the suite"}]
        spend = spend_of_lines(
            self,
            [
                assistant("msg_suite", "2026-10-16T10:00:00Z", {"output_tokens": 100}, content=thinking),
                assistant("msg_suite", "2026-10-16T10:00:01Z", {"output_tokens": 100}, content=bash("toolu_suite", chained)),
                tool_result("toolu_suite", "2026-10-16T10:01:30Z"),
            ],
        )
        self.assertEqual(step_named(spend, "suite")["output"], 100)
        self.assertEqual(spend["shared"]["tokens"], 0)

    def test_a_mark_ended_by_a_newline_counts(self):
        command = "lighthouse mark --results R --step change start\nlighthouse change --repo X; lighthouse mark --results R --step change end"
        spend = spend_of_lines(
            self,
            [
                assistant("msg_change", "2026-10-16T10:00:00Z", {"output_tokens": 100}, content=bash("toolu_change", command)),
                tool_result("toolu_change", "2026-10-16T10:00:05Z"),
            ],
        )
        self.assertEqual(step_named(spend, "change")["output"], 100)

    def test_spend_writes_spend_json_with_results_and_repo(self):
        home = scratch.make_home(self)
        repo, _ = scratch.make_repo(self)
        results = scratch.temporary_folder(self, "lh-results-")
        work = os.path.join(results, "work")
        write_session(home, work, "child.jsonl", [assistant("msg_child", "2026-10-16T10:00:00Z", {"output_tokens": 11}, cwd=work)])
        spend = spend_of(self, ["--results", results, "--repo", repo], home)
        with open(os.path.join(results, "spend.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), spend)


if __name__ == "__main__":
    unittest.main()
