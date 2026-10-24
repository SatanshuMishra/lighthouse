import http.server
import json
import os
import shlex
import socket
import threading
import time
import unittest

from tests import scratch


def wait(test, *arguments):
    env = scratch.environment(scratch.make_home(test))
    started = time.monotonic()
    code, stdout, stderr = scratch.run_lighthouse(["wait", *arguments], env)
    return code, stdout, stderr, time.monotonic() - started


def ready_profile(test, ready):
    path = os.path.join(scratch.temporary_folder(test, "lh-ready-"), "profile.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({**scratch.sample_profile(), "start": {"command": "true", "ready": ready}}, handle)
    return path


def closed_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Healthy(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *arguments):
        return


def serving(test):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Healthy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    return server.server_address[1]


class WaitTest(unittest.TestCase):
    def test_wait_reads_a_log_line_ready_from_the_profile(self):
        profile = ready_profile(self, "Server's ready on 4100")
        log = os.path.join(os.path.dirname(profile), "feature-start.log")
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("booting\nServer's ready on 4100\n")
        code, stdout, stderr, _ = wait(self, "--ready", "line", "--profile", profile, "--log", log, "--every", "1", "--within", "2")
        self.assertEqual(code, 0, stderr)
        self.assertIs(json.loads(stdout)["ready"], True)

    def test_wait_reads_a_url_ready_without_a_shell(self):
        down = ready_profile(self, "http://127.0.0.1:{}/health?a=1&b=2".format(closed_port()))
        code, stdout, stderr, _ = wait(self, "--ready", "url", "--profile", down, "--every", "1", "--within", "2")
        self.assertEqual(code, 0, stderr)
        self.assertIs(json.loads(stdout)["ready"], False)
        up = ready_profile(self, "http://127.0.0.1:{}/health?a=1&b=2".format(serving(self)))
        code, stdout, stderr, _ = wait(self, "--ready", "url", "--profile", up, "--every", "1", "--within", "2")
        self.assertEqual(code, 0, stderr)
        self.assertIs(json.loads(stdout)["ready"], True)

    def test_wait_refuses_a_ready_check_it_cannot_build(self):
        log_ready = ready_profile(self, "Listening on 4100")
        refused = {
            "url kind for a log line": ["--ready", "url", "--profile", log_ready],
            "line kind without a log": ["--ready", "line", "--profile", log_ready],
            "ready without a profile": ["--ready", "command"],
            "both until and ready": ["--until", "true", "--ready", "command", "--profile", log_ready],
            "neither until nor ready": [],
        }
        for case, arguments in refused.items():
            with self.subTest(case=case):
                code, stdout, stderr, _ = wait(self, *arguments)
                self.assertEqual(code, 2, stderr)
                self.assertIn("error", json.loads(stdout))

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
