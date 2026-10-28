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


def limits_file(test, deadline):
    path = os.path.join(scratch.temporary_folder(test, "lh-limits-"), "limits.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"suite_seconds": 60, "check_seconds": 60, "child_seconds": 120, "run_seconds": 720, "deadline": deadline}, handle)
    return path


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


def not_http(test):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    test.addCleanup(listener.close)

    def answer():
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                connection.sendall(b"SSH-2.0-OpenSSH_9\r\n")

    threading.Thread(target=answer, daemon=True).start()
    return listener.getsockname()[1]


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

    def test_wait_ready_polls_the_build_s_own_port(self):
        other_build = serving(self)
        own_build_down, own_build_up = closed_port(), serving(self)
        command = "python3 -c \"import urllib.request as u; u.urlopen('http://127.0.0.1:{}/health', timeout=1)\"".format(other_build)
        readies = {
            "url": ready_profile(self, "http://127.0.0.1:{}/health?a=1&b=2".format(other_build)),
            "command": ready_profile(self, command),
        }
        for kind, profile in readies.items():
            for own_port, expected in ((own_build_down, False), (own_build_up, True)):
                with self.subTest(kind=kind, ready=expected):
                    port = "{}={}".format(other_build, own_port)
                    code, stdout, stderr, _ = wait(
                        self, "--ready", kind, "--profile", profile, "--port", port, "--every", "1", "--within", "2"
                    )
                    self.assertEqual(code, 0, stderr)
                    self.assertIs(json.loads(stdout)["ready"], expected)

    def test_wait_ready_line_looks_for_the_build_s_own_port(self):
        profile = ready_profile(self, "Listening on 4100")
        log = os.path.join(os.path.dirname(profile), "feature-start.log")
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("Listening on 4101\n")
        code, stdout, stderr, _ = wait(
            self, "--ready", "line", "--profile", profile, "--log", log, "--port", "4100=4101", "--every", "1", "--within", "2"
        )
        self.assertEqual(code, 0, stderr)
        self.assertIs(json.loads(stdout)["ready"], True)

    def test_wait_answers_every_url_ready_with_json(self):
        refused = {
            "unexpanded port": "http://localhost:$PORT/health",
            "unclosed bracket": "http://[::1/health",
            "space in the path": "http://localhost:1/he alth",
        }
        for case, ready in refused.items():
            with self.subTest(case=case):
                code, stdout, stderr, _ = wait(self, "--ready", "url", "--profile", ready_profile(self, ready), "--within", "1")
                self.assertEqual(code, 2, stderr)
                self.assertIn("start.ready", json.loads(stdout)["error"])
                self.assertNotIn("Traceback", stderr)
        code, stdout, stderr, _ = wait(
            self, "--ready", "url", "--profile", ready_profile(self, "http://127.0.0.1:{}/".format(not_http(self))),
            "--every", "1", "--within", "2",
        )
        self.assertEqual(code, 0, stderr)
        self.assertIs(json.loads(stdout)["ready"], False)
        self.assertNotIn("Traceback", stderr)

    def test_wait_names_why_it_cannot_read_the_profile(self):
        folder = scratch.temporary_folder(self, "lh-ready-")
        cut_short = os.path.join(folder, "cut.json")
        with open(cut_short, "w", encoding="utf-8") as handle:
            handle.write('{"start": {"ready": "http://127.0.0.1:1/"')
        reasons = {os.path.join(folder, "missing.json"): "cannot read", cut_short: "is not valid JSON"}
        for path, reason in reasons.items():
            with self.subTest(reason=reason):
                code, stdout, stderr, _ = wait(self, "--ready", "url", "--profile", path)
                self.assertEqual(code, 2, stderr)
                self.assertIn(reason, json.loads(stdout)["error"])

    def test_wait_refuses_a_ready_check_it_cannot_build(self):
        log_ready = ready_profile(self, "Listening on 4100")
        refused = {
            "url kind for a log line": ["--ready", "url", "--profile", log_ready],
            "line kind without a log": ["--ready", "line", "--profile", log_ready],
            "ready without a profile": ["--ready", "command"],
            "both until and ready": ["--until", "true", "--ready", "command", "--profile", log_ready],
            "neither until nor ready": [],
            "port with until": ["--until", "true", "--port", "4100=4101"],
            "port out of range": ["--ready", "command", "--profile", log_ready, "--port", "4100=70000"],
            "port without a pair": ["--ready", "command", "--profile", log_ready, "--port", "4101"],
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
        self.assertNotIn("expired", report)

    def test_wait_with_limits_reports_a_ready_check_unexpired(self):
        code, stdout, stderr, _ = wait(self, "--until", "true", "--limits", limits_file(self, time.time() + 600))

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        self.assertIs(report["ready"], True)
        self.assertIs(report["expired"], False)

    def test_wait_with_limits_reports_a_window_before_the_deadline_unexpired(self):
        limits = limits_file(self, time.time() + 600)
        code, stdout, stderr, _ = wait(self, "--until", "exit 1", "--within", "1", "--limits", limits)

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        self.assertIs(report["ready"], False)
        self.assertIs(report["expired"], False)

    def test_wait_with_limits_ends_its_window_at_the_deadline(self):
        limits = limits_file(self, time.time() + 2)
        code, stdout, stderr, elapsed = wait(self, "--until", "exit 1", "--every", "1", "--limits", limits)

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        self.assertIs(report["ready"], False)
        self.assertIs(report["expired"], True)
        self.assertLess(elapsed, 10)

    def test_wait_refuses_a_window_over_540(self):
        code, stdout, _, _ = wait(self, "--until", "true", "--within", "541")

        self.assertEqual(code, 2)
        self.assertIn("--within", json.loads(stdout)["error"])


if __name__ == "__main__":
    unittest.main()
