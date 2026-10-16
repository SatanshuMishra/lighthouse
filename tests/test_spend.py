import json
import os
import unittest

from tests import scratch


def assistant(identifier, timestamp, usage):
    return json.dumps(
        {"type": "assistant", "timestamp": timestamp, "message": {"id": identifier, "usage": usage}}
    )


def write_transcript(folder, relative_path, lines):
    path = os.path.join(folder, relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


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
            spend,
            {
                "input": 15,
                "cache_creation": 20,
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


if __name__ == "__main__":
    unittest.main()
