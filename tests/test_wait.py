import json
import os
import shlex
import time
import unittest

from tests import scratch


def wait(test, *arguments):
    env = scratch.environment(scratch.make_home(test))
    started = time.monotonic()
    code, stdout, stderr = scratch.run_lighthouse(["wait", *arguments], env)
    return code, stdout, stderr, time.monotonic() - started


class WaitTest(unittest.TestCase):
    def test_wait_returns_when_the_check_passes(self):
        folder = scratch.temporary_folder(self, "lh-wait-")
        calls = os.path.join(folder, "calls")
        first_call = os.path.join(folder, "first-call")
        check = "echo call >> {calls}; test -e {first} || {{ touch {first}; exit 1; }}".format(
            calls=shlex.quote(calls), first=shlex.quote(first_call)
        )

        code, stdout, stderr, elapsed = wait(self, "--until", check, "--every", "1")

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        self.assertIs(report["ready"], True)
        self.assertLess(report["seconds"], 5)
        self.assertLess(elapsed, 5)
        with open(calls, encoding="utf-8") as handle:
            self.assertEqual(len(handle.read().splitlines()), 2)

    def test_wait_returns_after_its_window(self):
        code, stdout, stderr, elapsed = wait(self, "--until", "exit 1", "--every", "1", "--within", "2")

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        self.assertIs(report["ready"], False)
        self.assertAlmostEqual(report["seconds"], 2, delta=0.5)
        self.assertGreaterEqual(elapsed, 2)
        self.assertLess(elapsed, 3)

    def test_wait_refuses_a_window_over_540(self):
        code, stdout, _, _ = wait(self, "--until", "true", "--within", "541")

        self.assertEqual(code, 2)
        self.assertIn("--within", json.loads(stdout)["error"])


if __name__ == "__main__":
    unittest.main()
