import os
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, NamedTuple, Optional, Sequence, Set

FORWARDED_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
SIGNAL_EXIT_BASE = 128
LISTING = ["ps", "-A", "-o", "pid=,ppid="]
LISTING_SECONDS = 10
UNREAPED_POLL_SECONDS = 0.05

Handler = Any

owned_processes: Set["subprocess.Popen[bytes]"] = set()
owned_lock = threading.RLock()
stop_begun = threading.Event()
holding = threading.local()
held_signals: List[int] = []


class StopBegun(Exception):
    pass


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
        send_group(process.pid, signal.SIGKILL)
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
        stop_begun.set()
        listed = list(owned_processes)
    for process in listed:
        kill_tree(process)


class Forwarder(NamedTuple):
    previous: Handler

    def __call__(self, number: int, frame: Any) -> None:
        if getattr(holding, "depth", 0):
            held_signals.append(number)
            return
        if not callable(self.previous):
            kill_owned()
            raise SystemExit(SIGNAL_EXIT_BASE + number)
        try:
            self.previous(number, frame)
        except BaseException:
            kill_owned()
            raise


def forwarding() -> Dict[int, Handler]:
    if threading.current_thread() is not threading.main_thread():
        return {}
    previous = {number: signal.getsignal(number) for number in FORWARDED_SIGNALS}
    replaced = {
        number: handler
        for number, handler in previous.items()
        if handler not in (None, signal.SIG_IGN) and not isinstance(handler, Forwarder)
    }
    for number, handler in replaced.items():
        signal.signal(number, Forwarder(handler))
    return replaced


def restored(saved: Dict[int, Handler]) -> None:
    for number, handler in saved.items():
        signal.signal(number, handler)


@contextmanager
def held() -> Iterator[None]:
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    holding.depth = getattr(holding, "depth", 0) + 1
    try:
        yield
    finally:
        holding.depth -= 1
        if not holding.depth:
            arrived = list(held_signals)
            del held_signals[:]
            for number in arrived:
                signal.raise_signal(number)


@contextmanager
def guarded() -> Iterator[None]:
    saved = forwarding()
    try:
        yield
    finally:
        if saved:
            with held():
                restored(saved)
                stop_begun.clear()


def registered(process: "subprocess.Popen[bytes]") -> None:
    with owned_lock:
        owned_processes.add(process)
        refused = stop_begun.is_set()
    if refused:
        raise StopBegun("a stop began before {} could start".format(process.args))


def released(process: "subprocess.Popen[bytes]", grace_seconds: float) -> None:
    with owned_lock:
        owned_processes.discard(process)
    stop(process, grace_seconds)


def spawned(command: List[str], options: Dict[str, Any]) -> "subprocess.Popen[bytes]":
    process = subprocess.Popen(command, start_new_session=True, **options)
    try:
        registered(process)
    except BaseException:
        released(process, 0.0)
        raise
    return process


@contextmanager
def started(command: List[str], grace_seconds: float, **options: Any) -> Iterator["subprocess.Popen[bytes]"]:
    with guarded():
        with held():
            process = spawned(command, options)
        try:
            yield process
        finally:
            with held():
                released(process, grace_seconds)


def in_parallel(calls: Sequence[Callable[[], Any]]) -> List[Any]:
    with guarded(), ThreadPoolExecutor(max_workers=max(1, len(calls))) as pool:
        with held():
            futures = [pool.submit(call) for call in calls]
        return [future.result() for future in futures]
