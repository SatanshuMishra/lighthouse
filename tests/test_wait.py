import http.server
import json
import os
import shlex
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from lighthouse_tool import wait as waiting
from tests import scratch

WAIT_SECONDS = 120
EXIT_AFTER_SECONDS = 1.5


def write_later(test, path, text, seconds):
    def write():
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    timer = threading.Timer(seconds, write)
    timer.start()
    test.addCleanup(timer.cancel)


def wait(test, *arguments, exit_status=None, exit_file=None):
    env = scratch.environment(scratch.make_home(test))
    named = exit_file or os.path.join(scratch.temporary_folder(test, "lh-exit-"), "start.exit")
    if exit_status is not None:
        write_later(test, named, exit_status, EXIT_AFTER_SECONDS)
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, scratch.LIGHTHOUSE, "wait", *arguments, "--exit-file", named],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        test.fail("lighthouse wait did not end within {} seconds".format(WAIT_SECONDS))
    return process.returncode, stdout, stderr, time.monotonic() - started


def bare_wait(test, *arguments):
    env = scratch.environment(scratch.make_home(test))
    return scratch.run_lighthouse(["wait", *arguments], env)


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
        code, stdout, stderr, _ = wait(self, "--ready", "line", "--profile", profile, "--log", log, "--every", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["ready"], True)
        self.assertEqual(json.loads(stdout)["exited"], False)

    def test_wait_reads_a_url_ready_without_a_shell(self):
        down = ready_profile(self, "http://127.0.0.1:{}/health?a=1&b=2".format(closed_port()))
        code, stdout, stderr, _ = wait(self, "--ready", "url", "--profile", down, "--every", "0.2", exit_status="0\n")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["ready"], False)
        self.assertEqual(json.loads(stdout)["exited"], True)
        up = ready_profile(self, "http://127.0.0.1:{}/health?a=1&b=2".format(serving(self)))
        code, stdout, stderr, _ = wait(self, "--ready", "url", "--profile", up, "--every", "0.2")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["ready"], True)

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
                        self, "--ready", kind, "--profile", profile, "--port", port, "--every", "0.2", exit_status="1\n"
                    )
                    self.assertEqual(code, 0, stderr)
                    self.assertEqual(json.loads(stdout)["ready"], expected)
                    self.assertEqual(json.loads(stdout)["exited"], not expected)

    def test_wait_ready_line_looks_for_the_build_s_own_port(self):
        profile = ready_profile(self, "Listening on 4100")
        log = os.path.join(os.path.dirname(profile), "feature-start.log")
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("Listening on 4101\n")
        code, stdout, stderr, _ = wait(
            self, "--ready", "line", "--profile", profile, "--log", log, "--port", "4100=4101", "--every", "1"
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["ready"], True)

    def test_wait_answers_every_url_ready_with_json(self):
        refused = {
            "unexpanded port": "http://localhost:$PORT/health",
            "unclosed bracket": "http://[::1/health",
            "space in the path": "http://localhost:1/he alth",
        }
        for case, ready in refused.items():
            with self.subTest(case=case):
                code, stdout, stderr, _ = wait(self, "--ready", "url", "--profile", ready_profile(self, ready))
                self.assertEqual(code, 2, stderr)
                self.assertIn("start.ready", json.loads(stdout)["error"])
                self.assertNotIn("Traceback", stderr)
        code, stdout, stderr, _ = wait(
            self, "--ready", "url", "--profile", ready_profile(self, "http://127.0.0.1:{}/".format(not_http(self))),
            "--every", "0.2", exit_status="0\n",
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["ready"], False)
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
        self.assertEqual(report["ready"], True)
        self.assertEqual(report["exited"], False)
        self.assertNotIn("status", report)
        self.assertLess(report["seconds"], 5)
        self.assertLess(elapsed, 5)
        with open(calls, encoding="utf-8") as handle:
            self.assertEqual(len(handle.read().splitlines()), 2)

    def test_a_slow_check_runs_to_its_end(self):
        check = "sleep 2; true"

        code, stdout, stderr, _ = wait(self, "--until", check, "--every", "0.2")

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        self.assertEqual(report["ready"], True)
        self.assertGreaterEqual(report["seconds"], 2)

    def test_wait_ends_on_its_exit_file_with_the_status_it_holds(self):
        written = {"3\n": 3, "0": 0, "": None, "not a status\n": None}
        for text, status in written.items():
            with self.subTest(text=text):
                code, stdout, stderr, elapsed = wait(self, "--until", "exit 1", "--every", "0.2", exit_status=text)

                self.assertEqual(code, 0, stderr)
                report = json.loads(stdout)
                self.assertEqual(report, {"ready": False, "exited": True, "status": status, "seconds": report["seconds"]})
                self.assertGreaterEqual(elapsed, EXIT_AFTER_SECONDS)

    def test_wait_reads_the_exit_file_before_each_check(self):
        folder = scratch.temporary_folder(self, "lh-wait-")
        calls = os.path.join(folder, "calls")
        exit_file = os.path.join(folder, "start.exit")
        with open(exit_file, "w", encoding="utf-8") as handle:
            handle.write("2\n")

        code, stdout, stderr, _ = wait(
            self, "--until", "echo call >> {}".format(shlex.quote(calls)), "--every", "0.2", exit_file=exit_file
        )

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        self.assertEqual(report["exited"], True)
        self.assertEqual(report["status"], 2)
        self.assertFalse(os.path.exists(calls))

    def test_wait_refuses_a_window_a_deadline_and_a_missing_exit_file(self):
        folder = scratch.temporary_folder(self, "lh-wait-")
        exit_file = os.path.join(folder, "start.exit")
        refused = {
            "--within": ["--until", "true", "--exit-file", exit_file, "--within", "541"],
            "--limits": ["--until", "true", "--exit-file", exit_file, "--limits", os.path.join(folder, "limits.json")],
            "--exit-file": ["--until", "true"],
        }
        for named, arguments in refused.items():
            with self.subTest(named=named):
                code, stdout, stderr = bare_wait(self, *arguments)
                self.assertEqual(code, 2, stderr)
                self.assertIn(named, json.loads(stdout)["error"])
                self.assertNotIn("Traceback", stderr)

    def test_one_url_attempt_gives_up_after_sixty_silent_seconds(self):
        attempts = []

        def opened(opener, url, timeout):
            attempts.append(timeout)
            raise socket.timeout("timed out")

        with mock.patch("urllib.request.OpenerDirector.open", opened):
            answered = waiting.url_answers("http://127.0.0.1:1/health")

        self.assertIs(answered, False)
        self.assertEqual(attempts, [60])


if __name__ == "__main__":
    unittest.main()
