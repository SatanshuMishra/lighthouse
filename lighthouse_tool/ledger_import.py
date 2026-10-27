import datetime
import itertools
import json
import os
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from lighthouse_tool import metrics_writer, run_record, verdict
from lighthouse_tool.records import is_number, json_object

LEDGER = "runs.jsonl"
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
    handled = [handle_ledger(ledger, version, os.path.join(home, TRASH_FOLDER)) for ledger in ledgers(home)]
    lines = [line for outcome in handled for line in outcome.lines]
    code = 1 if any(outcome.failed for outcome in handled) else 0
    return code, "\n".join(lines) if lines else None, None


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
        if os.path.isdir(folder) and os.path.isfile(os.path.join(folder, LEDGER))
    ]


def handle_ledger(ledger: Ledger, version: Optional[str], trash: str) -> Handled:
    try:
        with open(ledger.path, encoding="utf-8") as handle:
            text_lines = handle.read().splitlines()
    except (OSError, ValueError) as error:
        return Handled(("not imported {}: {}".format(ledger.path, error),), True)
    numbered = [(number, text) for number, text in enumerate(text_lines, start=1) if text.strip()]
    parsed = [(number, json_object(text)) for number, text in numbered]
    skipped = tuple(
        "skipped {} line {}: not a JSON object".format(ledger.path, number) for number, line in parsed if line is None
    )
    groups = grouped([line for _, line in parsed if line is not None])
    imported = [import_group(ledger, group, version) for group in groups]
    import_lines = tuple(line for line, _ in imported)
    if any(failed for _, failed in imported):
        return Handled(skipped + import_lines, True)
    moved = trash_ledger(ledger, trash)
    return Handled(skipped + import_lines + moved.lines, moved.failed)


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


def import_group(ledger: Ledger, group: Group, version: Optional[str]) -> Tuple[str, bool]:
    times = [moment for moment in map(line_time, group.lines) if moment is not None]
    label = group.key if group.key is not None else "without a run"
    if not times:
        return "not imported {} run {}: no line holds a readable time".format(ledger.path, label), True
    run_id = metrics_writer.run_id(run_name(group.key), min(times))
    root = metrics_writer.store_root(os.environ)
    if os.path.lexists(metrics_writer.summary_path(root, run_record.PLUGIN, ledger.folder, run_id)):
        return "already in the store {} {}".format(ledger.folder, run_id), False
    fields = summary_fields(group, min(times), max(times))
    warning = metrics_writer.write_summary(run_record.PLUGIN, version, ledger.folder, run_id, fields)
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
            "carried": False,
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


def free_name(folder: str, name: str) -> str:
    stem, extension = os.path.splitext(name)
    copies = ("{} {}{}".format(stem, count, extension) for count in itertools.count(FIRST_COPY))
    candidates = (os.path.join(folder, candidate) for candidate in itertools.chain([name], copies))
    return next(candidate for candidate in candidates if not os.path.lexists(candidate))


def moved_to_trash(source: str, trash: str) -> Tuple[str, bool]:
    try:
        os.makedirs(trash, mode=0o700, exist_ok=True)
        destination = free_name(trash, os.path.basename(source))
        os.rename(source, destination)
    except OSError as error:
        return "not moved to the Trash {}: {}".format(source, error.strerror or error), True
    return "moved to the Trash {} -> {}".format(source, destination), False


def folder_is_empty(folder: str) -> bool:
    try:
        return not os.listdir(folder)
    except OSError:
        return False


def trash_ledger(ledger: Ledger, trash: str) -> Handled:
    line, failed = moved_to_trash(ledger.path, trash)
    folder = os.path.dirname(ledger.path)
    if failed or not folder_is_empty(folder):
        return Handled((line,), failed)
    folder_line, folder_failed = moved_to_trash(folder, trash)
    return Handled((line, folder_line), folder_failed)
