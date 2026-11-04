import os
import shlex
import signal
import subprocess
import sys
import time
import unittest

from tests import scratch

POLL_SECONDS = 0.05
PID_SECONDS = 10
INTERRUPT_GONE_SECONDS = 3
STOP_GRACE_SECONDS = 1.0
HOST_SECONDS = 10

INTERRUPTED_HOST = """
import os
import shlex
import sys
sys.path.insert(0, sys.argv[1])
from lighthouse_tool import launch
fifo, work = sys.argv[2], sys.argv[3]
command = "echo $$ > {} ; exec sleep 30".format(shlex.quote(fifo))
launch.run_child(["/bin/sh", "-c", command], work, "none", dict(os.environ))
"""

SLOW_SESSION_STEP = """
import shlex
import sys
sys.path.insert(0, sys.argv[1])
from lighthouse_tool import suite
marker, worktree, log_path = sys.argv[2], sys.argv[3], sys.argv[4]
check = "sleep 3; touch {}".format(shlex.quote(marker))
profile = {"suite": {"command": "true", "timeout_minutes": 0.01}}
ran = suite.run_step("check", check, worktree, "feature", log_path, profile, ())
sys.exit(ran.exit if ran.problem is None else 99)
"""

TERM_IGNORING_SERVER = "trap '' TERM; echo $$ > {pid}; while true; do sleep 0.1; done"

ISOLATED_HOST = """
import os
import shlex
import signal
import sys
sys.path.insert(0, sys.argv[1])
from lighthouse_tool import suite
signal.signal(signal.SIGINT, signal.default_int_handler)
signal.signal(signal.SIGTERM, signal.SIG_DFL)
signal.signal(signal.SIGHUP, signal.SIG_DFL)
folder, pids = sys.argv[2], sys.argv[3]
step = "echo $$ >> {} ; exec sleep 30".format(shlex.quote(pids))
profile = {"suite": {"command": "true", "isolated": True}, "setup": {"command": step}}
trees = {build: {"path": folder} for build in suite.BUILDS}
logs = {build: os.path.join(folder, build + ".log") for build in suite.BUILDS}
suite.both_builds(profile, (), trees, logs, None)
"""

WINDOW_HOST = """
import os
import signal
import sys
sys.path.insert(0, sys.argv[1])
from unittest import mock
from lighthouse_tool import process_tree, suite
signal.signal(signal.SIGTERM, signal.SIG_DFL)
folder, pids = sys.argv[2], sys.argv[3]
spawn = process_tree.subprocess.Popen


def spawned_then_signalled(command, *arguments, **options):
    process = spawn(command, *arguments, **options)
    if list(command[:2]) == ["/bin/sh", "-c"]:
        with open(pids, "a") as handle:
            handle.write(str(process.pid) + " ")
        os.kill(os.getpid(), signal.SIGTERM)
    return process


profile = {"suite": {"command": "true"}}
with mock.patch.object(process_tree.subprocess, "Popen", spawned_then_signalled):
    suite.run_step("setup", "exec sleep 30", folder, "core", os.path.join(folder, "core.log"), profile, ())
"""

NESTED_HOST = """
import os
import signal
import subprocess
import sys
import time
sys.path.insert(0, sys.argv[1])
from unittest import mock
from lighthouse_tool import process_tree
signal.signal(signal.SIGTERM, signal.SIG_DFL)
pids = sys.argv[3]
step = ["/bin/sh", "-c", "exec sleep 30"]


class SignalledOnNestedAdd(set):
    def add(self, process):
        super().add(process)
        with open(pids, "a") as handle:
            handle.write(str(process.pid) + " ")
        if len(self) == 2:
            os.kill(os.getpid(), signal.SIGTERM)


with mock.patch.object(process_tree, "owned_processes", SignalledOnNestedAdd()):
    with process_tree.started(step, 0.0, stdin=subprocess.DEVNULL):
        with process_tree.started(step, 0.0, stdin=subprocess.DEVNULL):
            time.sleep(30)
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


def turns_false_by(holds, deadline):
    while holds():
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)
    return True


def gone_by(pid, deadline):
    return turns_false_by(lambda: is_running(pid), deadline)


def is_zombie(pid):
    listed = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=PID_SECONDS,
        check=False,
    )
    return listed.stdout.decode("utf-8", errors="replace").strip().startswith("Z")


def ended_by(pid, deadline):
    return turns_false_by(lambda: is_running(pid) and not is_zombie(pid), deadline)


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


def written_pids(path, count, seconds):
    deadline = time.monotonic() + seconds
    found = []
    while len(found) < count and time.monotonic() < deadline:
        found = listed_pids(path)
        if len(found) < count:
            time.sleep(POLL_SECONDS)
    return found if len(found) >= count else None


def listed_pids(path):
    try:
        with open(path) as handle:
            return [int(word) for word in handle.read().split() if word.isdigit()]
    except OSError:
        return []


def kill_listed_quietly(path):
    for pid in listed_pids(path):
        kill_quietly(pid)


def started_host(test, script, folder, pids):
    host = subprocess.Popen(
        [sys.executable, "-c", script, scratch.ROOT, folder, pids],
        env=scratch.environment(scratch.make_home(test)),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    test.addCleanup(kill_listed_quietly, pids)
    test.addCleanup(stop_host, host)
    return host


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

    def test_a_slow_step_inside_the_child_runs_to_its_end(self):
        from lighthouse_tool import launch

        folder = scratch.temporary_folder(self, "lh-tree-")
        work = scratch.temporary_folder(self, "lh-work-")
        marker = os.path.join(folder, "finished")
        command = [sys.executable, "-c", SLOW_SESSION_STEP, scratch.ROOT, marker, folder, os.path.join(folder, "check.log")]

        ran = launch.run_child(command, work, "none", scratch.environment(scratch.make_home(self)))

        self.assertEqual((ran.exit, ran.problem), (0, None))
        self.assertGreaterEqual(ran.seconds, 3)
        self.assertTrue(os.path.exists(marker), "the slow check did not run to its end")

    def test_stop_pid_ends_a_started_process_and_its_children(self):
        from lighthouse_tool import process_tree

        folder = scratch.temporary_folder(self, "lh-tree-")
        pids = os.path.join(folder, "server.pid")
        script = "sh -c 'echo $$ > {pids}; exec sleep 600' < /dev/null & wait".format(pids=shlex.quote(pids))
        holder = subprocess.Popen(["/bin/sh", "-c", script], stdin=subprocess.DEVNULL)
        self.addCleanup(stop_host, holder)
        self.addCleanup(kill_listed_quietly, pids)
        found = written_pids(pids, 1, PID_SECONDS)
        self.assertIsNotNone(found, "the server never wrote its pid")
        server = found[0]
        self.assertEqual(process_tree.parents().get(server), holder.pid)

        stopped = process_tree.stop_pid(holder.pid, STOP_GRACE_SECONDS)

        self.assertIs(stopped, True)
        self.assertTrue(ended_by(server, time.monotonic() + HOST_SECONDS), "the server outlived its stop")
        self.assertIsNotNone(holder.wait(timeout=HOST_SECONDS))

    def test_stop_pid_kills_a_process_that_ignores_its_grace(self):
        from lighthouse_tool import process_tree

        folder = scratch.temporary_folder(self, "lh-tree-")
        pids = os.path.join(folder, "server.pid")
        server = subprocess.Popen(
            ["/bin/sh", "-c", TERM_IGNORING_SERVER.format(pid=shlex.quote(pids))], stdin=subprocess.DEVNULL
        )
        self.addCleanup(stop_host, server)
        self.assertIsNotNone(written_pids(pids, 1, PID_SECONDS), "the server never wrote its pid")
        started = time.monotonic()

        stopped = process_tree.stop_pid(server.pid, STOP_GRACE_SECONDS)

        self.assertIs(stopped, True)
        self.assertEqual(server.wait(timeout=HOST_SECONDS), -signal.SIGKILL)
        self.assertGreaterEqual(time.monotonic() - started, STOP_GRACE_SECONDS)

    def test_stop_pid_skips_a_process_that_has_already_exited(self):
        from lighthouse_tool import process_tree

        ended = subprocess.Popen(["true"], stdin=subprocess.DEVNULL)
        ended.wait(timeout=HOST_SECONDS)

        self.assertIs(process_tree.stop_pid(ended.pid, STOP_GRACE_SECONDS), False)

    def test_signalled_isolated_suite_stops_its_steps(self):
        for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            with self.subTest(signal=signal.Signals(number).name):
                folder = scratch.temporary_folder(self, "lh-tree-")
                pids = os.path.join(folder, "steps.pid")
                host = started_host(self, ISOLATED_HOST, folder, pids)
                found = written_pids(pids, 2, PID_SECONDS)
                self.assertIsNotNone(found, "the two builds' steps never wrote their pids")

                os.kill(host.pid, number)
                deadline = time.monotonic() + INTERRUPT_GONE_SECONDS
                alive = [pid for pid in found if not gone_by(pid, deadline)]

                for pid in alive:
                    kill_quietly(pid)
                self.assertEqual(alive, [], "steps outlived the signalled isolated suite")
                host.wait(timeout=HOST_SECONDS)

    def test_signal_between_start_and_ownership_stops_the_step(self):
        folder = scratch.temporary_folder(self, "lh-tree-")
        pids = os.path.join(folder, "step.pid")
        host = started_host(self, WINDOW_HOST, folder, pids)
        host.wait(timeout=HOST_SECONDS)
        found = written_pids(pids, 1, PID_SECONDS)
        self.assertIsNotNone(found, "the step was never spawned")

        deadline = time.monotonic() + INTERRUPT_GONE_SECONDS
        alive = [pid for pid in found if not gone_by(pid, deadline)]

        for pid in alive:
            kill_quietly(pid)
        self.assertEqual(alive, [], "the step outlived a signal sent before its ownership")

    def test_signal_while_nested_start_holds_the_lock_does_not_deadlock(self):
        folder = scratch.temporary_folder(self, "lh-tree-")
        pids = os.path.join(folder, "steps.pid")
        host = started_host(self, NESTED_HOST, folder, pids)

        code = host.wait(timeout=HOST_SECONDS)
        found = written_pids(pids, 2, PID_SECONDS)
        deadline = time.monotonic() + INTERRUPT_GONE_SECONDS
        alive = [pid for pid in found or [] if not gone_by(pid, deadline)]

        self.assertEqual(code, 128 + signal.SIGTERM)
        self.assertIsNotNone(found, "the nested steps never started")
        self.assertEqual(alive, [], "nested steps outlived the signal")

    def test_started_refuses_once_a_stop_has_begun(self):
        from unittest import mock

        from lighthouse_tool import process_tree

        spawn = subprocess.Popen
        steps = []

        def recorded(command, *arguments, **options):
            process = spawn(command, *arguments, **options)
            if command[:2] == ["/bin/sh", "-c"]:
                steps.append(process)
            return process

        def start_a_step():
            with process_tree.started(["/bin/sh", "-c", "exec sleep 30"], 0.0, stdin=subprocess.DEVNULL):
                return "started"

        with mock.patch.object(process_tree.subprocess, "Popen", recorded):
            with process_tree.guarded():
                process_tree.kill_owned()
                with self.assertRaises(process_tree.StopBegun):
                    process_tree.in_parallel([start_a_step])

        self.assertEqual(len(steps), 1)
        self.assertIsNotNone(steps[0].returncode)
        self.assertFalse(process_tree.stop_begun.is_set())

    def test_a_reaped_leader_still_has_its_group_stopped(self):
        from lighthouse_tool import process_tree

        folder = scratch.temporary_folder(self, "lh-tree-")
        pids = os.path.join(folder, "background.pid")
        self.addCleanup(kill_listed_quietly, pids)
        command = ["/bin/sh", "-c", "sleep 30 >/dev/null 2>&1 & echo $! > {}".format(shlex.quote(pids))]
        with process_tree.started(command, 0.0, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL) as process:
            process.wait(timeout=HOST_SECONDS)
        found = written_pids(pids, 1, PID_SECONDS)
        self.assertIsNotNone(found, "the step never wrote its background pid")

        ended = ended_by(found[0], time.monotonic() + INTERRUPT_GONE_SECONDS)

        self.assertTrue(ended, "the background process {} outlived its reaped leader".format(found[0]))

    def test_started_restores_the_callers_handlers(self):
        from lighthouse_tool import process_tree

        def caller_handler(number, frame):
            return None

        numbers = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        before = {number: signal.getsignal(number) for number in numbers}
        for number in numbers:
            self.addCleanup(signal.signal, number, before[number])
        signal.signal(signal.SIGTERM, caller_handler)
        expected = {number: signal.getsignal(number) for number in numbers}
        with process_tree.started(["/bin/sh", "-c", "exec sleep 30"], 0.0, stdin=subprocess.DEVNULL) as process:
            installed = {number: signal.getsignal(number) for number in numbers}

        self.assertNotEqual(installed[signal.SIGTERM], caller_handler)
        self.assertEqual({number: signal.getsignal(number) for number in numbers}, expected)
        self.assertIsNotNone(process.returncode)


class InheritedSignalMaskTest(unittest.TestCase):
    def test_started_steps_receive_the_signals_lighthouse_forwards(self):
        from lighthouse_tool import process_tree

        def self_terminating():
            command = ["/bin/sh", "-c", "kill -TERM $$; exit 0"]
            with process_tree.started(command, 0.0, stdin=subprocess.DEVNULL) as process:
                return process.wait(timeout=HOST_SECONDS)

        def in_a_worker():
            return process_tree.in_parallel([self_terminating])[0]

        for label, run in (("serial", self_terminating), ("parallel", in_a_worker)):
            with self.subTest(path=label):
                self.assertEqual(run(), -signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
