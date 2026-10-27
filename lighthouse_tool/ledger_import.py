import collections
import datetime
import errno
import itertools
import json
import os
from typing import Any, Callable, Dict, Iterator, List, Mapping, NamedTuple, Optional, Tuple

from lighthouse_tool import metrics_writer, run_record, verdict
from lighthouse_tool.records import is_number, json_object

LEDGER = "runs.jsonl"
CLAIM_SUFFIX = ".importing"
STATE_FOLDER = ".lighthouse"
TRASH_FOLDER = ".Trash"
USAGE = "usage: lighthouse metrics import"
RESULTS_SPEND = "results"
FIRST_COPY = 2


class Ledger(NamedTuple):
    folder: str
    path: str


class Group(NamedTuple):
    key: Optional[str]
    lines: Tuple[Dict[str, Any], ...]


class Handled(NamedTuple):
    lines: Tuple[str, ...]
    failed: bool


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    if argv[1:] != ["import"]:
        reason = "lighthouse metrics takes exactly one argument, import"
        return 2, json.dumps({"error": reason}), "lighthouse metrics: {}; {}".format(reason, USAGE)
    home = os.path.expanduser("~")
    version = run_record.plugin_version()
    environ = without_parent(os.environ)
    trash = os.path.join(home, TRASH_FOLDER)
    handled = [handle_ledger(ledger, version, trash, environ) for ledger in ledgers(home)]
    lines = [line for outcome in handled for line in outcome.lines]
    code = 1 if any(outcome.failed for outcome in handled) else 0
    return code, "\n".join(lines) if lines else None, None


def without_parent(environ: Mapping[str, str]) -> Dict[str, str]:
    return {name: value for name, value in environ.items() if name != metrics_writer.PARENT_VARIABLE}


def claimed_path(ledger: Ledger) -> str:
    return ledger.path + CLAIM_SUFFIX


def ledgers(home: str) -> List[Ledger]:
    state = os.path.join(home, STATE_FOLDER)
    try:
        names = sorted(os.listdir(state))
    except OSError:
        return []
    folders = [os.path.join(state, name) for name in names]
    return [
        Ledger(os.path.basename(folder), os.path.join(folder, LEDGER))
        for folder in folders
        if os.path.isdir(folder)
        and any(os.path.isfile(os.path.join(folder, LEDGER + suffix)) for suffix in ("", CLAIM_SUFFIX))
    ]


def moved_without_replacing(source: str, destination: str) -> None:
    os.link(source, destination)
    try:
        os.unlink(source)
    except OSError:
        os.unlink(destination)
        raise


def claimed(ledger: Ledger) -> str:
    claim = claimed_path(ledger)
    if not os.path.lexists(claim):
        moved_without_replacing(ledger.path, claim)
    return claim


def released(ledger: Ledger, claim: str, handled: Handled) -> Handled:
    try:
        moved_without_replacing(claim, ledger.path)
    except OSError as error:
        kept = "kept the claimed ledger {}: {}".format(claim, error.strerror or error)
        return Handled(handled.lines + (kept,), True)
    return handled


def clashes(groups: List[Group]) -> List[Tuple[str, int]]:
    counts = collections.Counter(run_id for run_id in map(group_run_id, groups) if run_id is not None)
    return sorted((run_id, count) for run_id, count in counts.items() if count > 1)


def handle_ledger(ledger: Ledger, version: Optional[str], trash: str, environ: Mapping[str, str]) -> Handled:
    try:
        claim = claimed(ledger)
        with open(claim, encoding="utf-8") as handle:
            text_lines = handle.read().splitlines()
    except (OSError, ValueError) as error:
        return Handled(("not imported {}: {}".format(ledger.path, error),), True)
    numbered = [(number, text) for number, text in enumerate(text_lines, start=1) if text.strip()]
    parsed = [(number, json_object(text)) for number, text in numbered]
    skipped = tuple(
        "skipped {} line {}: not a JSON object".format(ledger.path, number) for number, line in parsed if line is None
    )
    groups = grouped([line for _, line in parsed if line is not None])
    clashing = tuple(
        "not imported {}: {} runs share the run id {}".format(ledger.path, count, run_id)
        for run_id, count in clashes(groups)
    )
    if clashing:
        return released(ledger, claim, Handled(skipped + clashing, True))
    imported = [import_group(ledger, group, version, environ) for group in groups]
    import_lines = tuple(line for line, _ in imported)
    if any(failed for _, failed in imported):
        return released(ledger, claim, Handled(skipped + import_lines, True))
    moved = trash_ledger(ledger, claim, trash)
    handled = Handled(skipped + import_lines + moved.lines, moved.failed)
    return released(ledger, claim, handled) if os.path.lexists(claim) else handled


def run_key(line: Dict[str, Any]) -> Optional[str]:
    key = line.get("run")
    return key if isinstance(key, str) and key else None


def grouped(lines: List[Dict[str, Any]]) -> List[Group]:
    keys = list(dict.fromkeys(key for key in map(run_key, lines) if key is not None))
    keyed = {key: tuple(line for line in lines if run_key(line) == key) for key in keys}
    first_index = {key: next(index for index, line in enumerate(lines) if run_key(line) == key) for key in keys}
    entries = [(first_index[key], Group(key, keyed[key])) for key in keys] + [
        (index, Group(None, (line,))) for index, line in enumerate(lines) if run_key(line) is None
    ]
    return [group for _, group in sorted(entries, key=lambda entry: entry[0])]


def line_time(line: Dict[str, Any]) -> Optional[datetime.datetime]:
    value = line.get("time")
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return moment.replace(tzinfo=datetime.timezone.utc) if moment.tzinfo is None else moment


def run_name(key: Optional[str]) -> str:
    return run_record.run_name(os.path.basename(key.rstrip("/")) if key is not None else None)


def group_times(group: Group) -> List[datetime.datetime]:
    return [moment for moment in map(line_time, group.lines) if moment is not None]


def group_run_id(group: Group) -> Optional[str]:
    times = group_times(group)
    return metrics_writer.run_id(run_name(group.key), min(times)) if times else None


def import_group(ledger: Ledger, group: Group, version: Optional[str], environ: Mapping[str, str]) -> Tuple[str, bool]:
    times = group_times(group)
    run_id = group_run_id(group)
    label = group.key if group.key is not None else "without a run"
    if run_id is None:
        return "not imported {} run {}: no line holds a readable time".format(ledger.path, label), True
    root = metrics_writer.store_root(environ)
    if os.path.lexists(metrics_writer.summary_path(root, run_record.PLUGIN, ledger.folder, run_id)):
        return "already in the store {} {}".format(ledger.folder, run_id), False
    fields = summary_fields(group, min(times), max(times))
    warning = metrics_writer.write_summary(run_record.PLUGIN, version, ledger.folder, run_id, fields, environ=environ)
    if warning is not None:
        return "not imported {} run {}: {}".format(ledger.path, label, warning), True
    return "imported {} {}".format(ledger.folder, run_id), False


def last_of_kind(group: Group, kind: str) -> Dict[str, Any]:
    return next((line for line in reversed(group.lines) if line.get("kind") == kind), {})


def number(value: Any) -> Optional[float]:
    return value if is_number(value) else None


def integer(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def as_object(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def token_kinds(entry: Any) -> Optional[Dict[str, int]]:
    found = as_object(entry) or {}
    counts = {kind: integer(found.get(kind)) for kind in metrics_writer.TOKEN_KINDS}
    return counts if all(count is not None for count in counts.values()) else None


def spent(entry: Any) -> Optional[Dict[str, Any]]:
    found = as_object(entry)
    return {"usd": number(found.get("dollars")), "tokens": token_kinds(found)} if found is not None else None


def phase_seconds(phases: Any) -> Optional[Dict[str, Any]]:
    found = as_object(phases)
    if found is None:
        return None
    return {
        "prepare_seconds": run_record.seconds(found.get("prepare_minutes")),
        "suite_seconds": run_record.seconds(found.get("suite_minutes")),
        "rerun_seconds": run_record.seconds(found.get("rerun_minutes")),
        "reused": None,
    }


def suite_summary(suite: Any) -> Optional[Dict[str, Any]]:
    found = as_object(suite)
    if found is None:
        return None
    return {
        "result": None,
        "reason": None,
        "failures": None,
        "pre_existing": None,
        "flaky": None,
        **{build: phase_seconds(found.get(build)) for build in verdict.BUILDS},
    }


def check_kind(check: Any) -> Optional[str]:
    kind = check.get("kind") if isinstance(check, dict) else check
    return run_record.choice(kind, verdict.CHECK_KINDS)


def paths_summary(paths: Any) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(paths, list):
        return None
    return [
        {
            "name": run_record.text(path.get("name")),
            "kind": run_record.choice(path.get("kind"), verdict.PATH_KINDS),
            "status": run_record.choice(path.get("status"), verdict.PATH_STATUSES),
            "check": check_kind(path.get("check")),
            "retry": None,
            "carried": None,
        }
        for path in paths
        if isinstance(path, dict)
    ]


def group_rows(groups: Any, label: str) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(groups, list):
        return None
    return [
        {
            label: run_record.text(entry.get("name")),
            "build": run_record.choice(entry.get("build"), verdict.BUILDS),
            "elapsed_seconds": run_record.seconds(entry.get("minutes")),
            "usd": number(entry.get("dollars")),
            "tokens": token_kinds(entry),
        }
        for entry in groups
        if isinstance(entry, dict)
    ]


def models_summary(models: Any) -> Optional[List[Dict[str, Any]]]:
    found = as_object(models)
    if found is None:
        return None
    return [
        {"model": model, "tokens": token_kinds(entry), "usd": number((as_object(entry) or {}).get("dollars"))}
        for model, entry in found.items()
    ]


def unpriced_summary(unpriced: Any) -> Optional[List[str]]:
    if not isinstance(unpriced, list):
        return None
    return [model for model in unpriced if isinstance(model, str)]


def waiting_summary(waiting: Any) -> Optional[Dict[str, Any]]:
    found = as_object(waiting)
    if found is None:
        return None
    return {
        "person_seconds": run_record.seconds(found.get("person")),
        "tool_seconds": run_record.seconds(found.get("tool")),
        "model_seconds": run_record.seconds(found.get("model")),
    }


def rewrites_summary(expired: Any) -> Optional[Dict[str, Any]]:
    found = as_object(expired)
    if found is None:
        return None
    return {"count": integer(found.get("count")), "cache_write": integer(found.get("tokens"))}


def spend_summary(spend: Any) -> Dict[str, Any]:
    found = as_object(spend)
    if found is None:
        return dict.fromkeys(run_record.SPEND_FIELDS)
    return {
        "usd": number(found.get("dollars")),
        "price_date": None,
        "tokens": token_kinds(found),
        "messages": integer(found.get("messages")),
        "models": models_summary(found.get("models")),
        "unpriced": unpriced_summary(found.get("unpriced")),
        "steps": group_rows(found.get("steps"), "step"),
        "drives": group_rows(found.get("paths"), "path"),
        "shared": spent(found.get("shared")),
        "caller": None,
        "waiting": waiting_summary(found.get("waiting")),
        "expired_rewrites": rewrites_summary(found.get("expired_rewrites")),
    }


def summary_fields(group: Group, start: datetime.datetime, end: datetime.datetime) -> Dict[str, Any]:
    last = group.lines[-1]
    launch = last_of_kind(group, "launch")
    verdict_line = last_of_kind(group, "verdict")
    commits = as_object(verdict_line.get("commits")) or {}
    return {
        "started": run_record.stamp(start),
        "ended": run_record.stamp(end),
        "run_seconds": run_record.seconds(launch.get("minutes")),
        "verdict": run_record.choice(last.get("verdict"), run_record.VERDICTS),
        "reason": run_record.text(last.get("reason")),
        "core": None,
        "feature": None,
        "core_commit": run_record.text(commits.get("core")),
        "feature_commit": run_record.text(commits.get("feature")),
        "retest": None,
        "final": None,
        "spec": None,
        "failures": None,
        "unproven": None,
        "flaky": None,
        "build": None,
        "suite": suite_summary(verdict_line.get("suite")),
        "paths": paths_summary(verdict_line.get("paths")),
        **spend_summary(verdict_line.get("spend")),
        "child_exit": None,
        "child_session": None,
        "results": None,
        "spend_scope": RESULTS_SPEND,
        "imported": True,
    }


def trash_names(name: str) -> Iterator[str]:
    stem, extension = os.path.splitext(name)
    copies = ("{} {}{}".format(stem, count, extension) for count in itertools.count(FIRST_COPY))
    return itertools.chain([name], copies)


def placed_at(destination: str, place: Callable[[str], None]) -> Optional[str]:
    try:
        place(destination)
    except FileExistsError:
        return None
    return destination


def placed_in_trash(trash: str, name: str, place: Callable[[str], None]) -> str:
    os.makedirs(trash, mode=0o700, exist_ok=True)
    attempts = (placed_at(os.path.join(trash, candidate), place) for candidate in trash_names(name))
    return next(destination for destination in attempts if destination is not None)


def moved_to_trash(ledger: Ledger, claim: str, trash: str) -> Tuple[str, bool]:
    try:
        destination = placed_in_trash(trash, LEDGER, lambda target: moved_without_replacing(claim, target))
    except OSError as error:
        return "not moved to the Trash {}: {}".format(ledger.path, error.strerror or error), True
    return "moved to the Trash {} -> {}".format(ledger.path, destination), False


def folder_moved_to_trash(folder: str, trash: str) -> Optional[Tuple[str, bool]]:
    try:
        destination = placed_in_trash(trash, os.path.basename(folder), lambda target: os.mkdir(target, 0o700))
    except OSError as error:
        return "not moved to the Trash {}: {}".format(folder, error.strerror or error), True
    try:
        os.rmdir(folder)
    except OSError as error:
        os.rmdir(destination)
        if error.errno in (errno.ENOTEMPTY, errno.EEXIST):
            return None
        return "not moved to the Trash {}: {}".format(folder, error.strerror or error), True
    return "moved to the Trash {} -> {}".format(folder, destination), False


def trash_ledger(ledger: Ledger, claim: str, trash: str) -> Handled:
    line, failed = moved_to_trash(ledger, claim, trash)
    if failed:
        return Handled((line,), failed)
    folder_outcome = folder_moved_to_trash(os.path.dirname(claim), trash)
    if folder_outcome is None:
        return Handled((line,), False)
    folder_line, folder_failed = folder_outcome
    return Handled((line, folder_line), folder_failed)
