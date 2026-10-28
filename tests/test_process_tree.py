import os
import signal
import subprocess
import sys
import time
import unittest

from tests import scratch

POLL_SECONDS = 0.05
PID_SECONDS = 10
INTERRUPT_GONE_SECONDS = 3
LIMIT_GONE_SECONDS = 2
MARKER_SECONDS = 10
HOST_SECONDS = 10

INTERRUPTED_HOST = """
import os
import shlex
import sys
sys.path.insert(0, sys.argv[1])
from lighthouse_tool import launch
fifo, work = sys.argv[2], sys.argv[3]
command = "echo $$ > {} ; exec sleep 30".format(shlex.quote(fifo))
launch.run_child(["/bin/sh", "-c", command], work, "none", dict(os.environ), 60)
"""

SESSION_STEP = """
import os
import shlex
import sys
sys.path.insert(0, sys.argv[1])
from unittest import mock
from lighthouse_tool import limits, suite
fifo, marker, worktree, log_path = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
forked = os.fork()
if forked:
    os.waitpid(forked, 0)
    sys.exit(0)
os.setsid()
quiet = os.open(os.devnull, os.O_RDWR)
for descriptor in (0, 1, 2):
    os.dup2(quiet, descriptor)
measured = limits.of
check = "echo $$ > {} ; sleep 8; touch {}".format(shlex.quote(fifo), shlex.quote(marker))
profile = {"suite": {"command": "true"}}
with mock.patch.object(limits, "of", lambda found: measured(found)._replace(check_seconds=3)):
    suite.run_step("check", check, worktree, "feature", log_path, profile, ())
os._exit(0)
"""


def fifo_reader(test, path):
    os.mkfifo(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    test.addCleanup(os.close, descriptor)
    return descriptor


def written_pid(descriptor, seconds):
    deadline = time.monotonic() + seconds
    text = b""
    while b"\n" not in text and time.monotonic() < deadline:
        try:
            chunk = os.read(descriptor, 64)
        except BlockingIOError:
            chunk = b""
        if not chunk:
            time.sleep(POLL_SECONDS)
        text += chunk
    return int(text.split(b"\n")[0]) if b"\n" in text else None


def is_running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def gone_by(pid, deadline):
    while is_running(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)
    return True


def kill_quietly(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def stop_host(host):
    if host.poll() is None:
        try:
            os.killpg(host.pid, signal.SIGKILL)
        except OSError:
            pass
        host.wait(timeout=HOST_SECONDS)


class ProcessTreeTest(unittest.TestCase):
    def test_interrupted_launch_stops_the_child(self):
        folder = scratch.temporary_folder(self, "lh-tree-")
        work = scratch.temporary_folder(self, "lh-work-")
        fifo = os.path.join(folder, "child.pid")
        reader = fifo_reader(self, fifo)
        host = subprocess.Popen(
            [sys.executable, "-c", INTERRUPTED_HOST, scratch.ROOT, fifo, work],
            env=scratch.environment(scratch.make_home(self)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.addCleanup(stop_host, host)
        pid = written_pid(reader, PID_SECONDS)
        self.assertIsNotNone(pid, "the child never wrote its pid")

        os.killpg(host.pid, signal.SIGINT)
        gone = gone_by(pid, time.monotonic() + INTERRUPT_GONE_SECONDS)

        if not gone:
            kill_quietly(pid)
        self.assertTrue(gone, "the child {} outlived the interrupted launch".format(pid))
        host.wait(timeout=HOST_SECONDS)

    def test_child_limit_stops_its_steps(self):
        from lighthouse_tool import launch

        folder = scratch.temporary_folder(self, "lh-tree-")
        work = scratch.temporary_folder(self, "lh-work-")
        fifo = os.path.join(folder, "check.pid")
        marker = os.path.join(folder, "finished")
        reader = fifo_reader(self, fifo)
        command = [
            sys.executable, "-c", SESSION_STEP,
            scratch.ROOT, fifo, marker, folder, os.path.join(folder, "check.log"),
        ]
        started = time.monotonic()

        launch.run_child(command, work, "none", scratch.environment(scratch.make_home(self)), 1)
        returned = time.monotonic()
        pid = written_pid(reader, PID_SECONDS)
        self.assertIsNotNone(pid, "the check never wrote its pid")
        gone = gone_by(pid, returned + LIMIT_GONE_SECONDS)
        if not gone:
            kill_quietly(pid)
        time.sleep(max(0.0, started + MARKER_SECONDS - time.monotonic()))

        self.assertTrue(gone, "the check {} outlived the child's limit".format(pid))
        self.assertFalse(os.path.exists(marker), "the check finished after the child's limit")

    def test_owned_restores_the_callers_handlers(self):
        from lighthouse_tool import process_tree

        def caller_handler(number, frame):
            return None

        numbers = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        before = {number: signal.getsignal(number) for number in numbers}
        for number in numbers:
            self.addCleanup(signal.signal, number, before[number])
        signal.signal(signal.SIGTERM, caller_handler)
        expected = {number: signal.getsignal(number) for number in numbers}
        process = process_tree.start(["/bin/sh", "-c", "exec sleep 30"], stdin=subprocess.DEVNULL)

        with process_tree.owned(process):
            installed = {number: signal.getsignal(number) for number in numbers}

        self.assertNotEqual(installed[signal.SIGTERM], caller_handler)
        self.assertEqual({number: signal.getsignal(number) for number in numbers}, expected)
        self.assertIsNotNone(process.returncode)


if __name__ == "__main__":
    unittest.main()
