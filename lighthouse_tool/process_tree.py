import os
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Set

FORWARDED_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
SIGNAL_EXIT_BASE = 128
LISTING = ["ps", "-A", "-o", "pid=,ppid="]
LISTING_SECONDS = 10
UNREAPED_POLL_SECONDS = 0.05

Handler = Any

owned_processes: Set["subprocess.Popen[bytes]"] = set()
owned_lock = threading.Lock()


def start(command: List[str], **options: Any) -> "subprocess.Popen[bytes]":
    return subprocess.Popen(command, start_new_session=True, **options)


def parents() -> Dict[int, int]:
    try:
        listed = subprocess.run(
            LISTING,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=LISTING_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    rows = [line.split() for line in listed.stdout.decode("utf-8", errors="replace").splitlines()]
    return {int(row[0]): int(row[1]) for row in rows if len(row) == 2 and row[0].isdigit() and row[1].isdigit()}


def send(pid: int, number: int) -> None:
    try:
        os.kill(pid, number)
    except OSError:
        pass


def send_group(leader: int, number: int) -> None:
    try:
        os.killpg(leader, number)
    except OSError:
        pass


def frozen_tree(root: int) -> Set[int]:
    send(root, signal.SIGSTOP)
    collected = {root}
    own = os.getpid()
    while True:
        found = {pid for pid, parent in parents().items() if parent in collected and pid not in collected and pid != own}
        if not found:
            return collected
        for pid in found:
            send(pid, signal.SIGSTOP)
        collected = collected | found


def has_exited(process: "subprocess.Popen[bytes]") -> bool:
    if process.returncode is not None:
        return True
    if not hasattr(os, "waitid"):
        return process.poll() is not None
    try:
        return os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    except ChildProcessError:
        return True


def exited_unreaped(process: "subprocess.Popen[bytes]", seconds: Optional[float]) -> None:
    if not hasattr(os, "waitid"):
        process.wait(timeout=seconds)
        return
    deadline = None if seconds is None else time.monotonic() + seconds
    while not has_exited(process):
        if deadline is not None and time.monotonic() > deadline:
            raise subprocess.TimeoutExpired(process.args, seconds or 0)
        time.sleep(UNREAPED_POLL_SECONDS)


def terminated_tree(process: "subprocess.Popen[bytes]", grace_seconds: float) -> Set[int]:
    listed = frozen_tree(process.pid)
    for pid in listed:
        send(pid, signal.SIGTERM)
    send_group(process.pid, signal.SIGTERM)
    for pid in listed:
        send(pid, signal.SIGCONT)
    try:
        exited_unreaped(process, grace_seconds)
    except subprocess.TimeoutExpired:
        pass
    remaining = parents()
    return {pid for pid in listed if pid in remaining and pid != process.pid}


def kill_tree(process: "subprocess.Popen[bytes]", grace_seconds: float = 0.0) -> None:
    if process.returncode is not None:
        return
    lingering = terminated_tree(process, grace_seconds) if grace_seconds > 0 else set()
    for pid in lingering:
        send(pid, signal.SIGSTOP)
    for pid in frozen_tree(process.pid) | lingering:
        send(pid, signal.SIGKILL)
    send_group(process.pid, signal.SIGKILL)


def stop(process: "subprocess.Popen[bytes]", grace_seconds: float = 0.0) -> None:
    kill_tree(process, grace_seconds)
    process.wait()


def kill_owned() -> None:
    with owned_lock:
        listed = list(owned_processes)
    for process in listed:
        kill_tree(process)


def forwarder(previous: Handler) -> Callable[[int, Any], None]:
    def forward(number: int, frame: Any) -> None:
        if not callable(previous):
            kill_owned()
            raise SystemExit(SIGNAL_EXIT_BASE + number)
        try:
            previous(number, frame)
        except BaseException:
            kill_owned()
            raise

    return forward


def forwarding() -> Dict[int, Handler]:
    if threading.current_thread() is not threading.main_thread():
        return {}
    previous = {number: signal.getsignal(number) for number in FORWARDED_SIGNALS}
    replaced = {number: handler for number, handler in previous.items() if handler not in (None, signal.SIG_IGN)}
    for number, handler in replaced.items():
        signal.signal(number, forwarder(handler))
    return replaced


def restored(saved: Dict[int, Handler]) -> None:
    for number, handler in saved.items():
        signal.signal(number, handler)


def blocked() -> Optional[Set[int]]:
    if not hasattr(signal, "pthread_sigmask"):
        return None
    return signal.pthread_sigmask(signal.SIG_BLOCK, FORWARDED_SIGNALS)


def unblocked(mask: Optional[Set[int]]) -> None:
    if mask is not None:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)


@contextmanager
def owned(process: "subprocess.Popen[bytes]", grace_seconds: float = 0.0) -> Iterator["subprocess.Popen[bytes]"]:
    with owned_lock:
        owned_processes.add(process)
    saved = forwarding()
    try:
        yield process
    finally:
        mask = blocked()
        try:
            with owned_lock:
                owned_processes.discard(process)
            stop(process, grace_seconds)
        finally:
            restored(saved)
            unblocked(mask)
