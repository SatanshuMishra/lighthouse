import argparse
import datetime
import json
import os
import re
from typing import Any, Dict, FrozenSet, List, Mapping, NamedTuple, Optional, Tuple

from lighthouse_tool import cli, mark, metrics_writer, spend, verdict
from lighthouse_tool.records import is_number, json_object
from lighthouse_tool.repo import Refusal, repository_folder

PLUGIN = "lighthouse"
CATALOGUE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "catalogue.json")
RUN_START = "run.start"
RUN_END = "run.end"
EMPTY_NAME = "run"
STAMP_LENGTH = len(".YYYYMMDDTHHMMSSZ")
UNSAFE_CHARACTER = re.compile(r"[^a-z0-9.-]")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
VERDICTS = ("green", "failures", "blocked", "unproven")
SUITE_RESULTS = ("passed", "failures", "blocked")
RETRY_OUTCOMES = ("passed", "failed")
OWN_SPEND = "own"
SECONDS_DIGITS = 3
SPEND_FIELDS = (
    "usd",
    "price_date",
    "tokens",
    "messages",
    "models",
    "unpriced",
    "steps",
    "drives",
    "shared",
    "caller",
    "waiting",
    "expired_rewrites",
)


class Recording(NamedTuple):
    repo: str
    run: str
    start: datetime.datetime
    plugin_version: Optional[str]
    environ: Mapping[str, str]
    start_fields: Dict[str, Any]
    warnings: Tuple[str, ...]


class Ending(NamedTuple):
    line: str
    reason: Optional[str]
    child_exit: Optional[int]
    child_session: Optional[str]


def run_name(feature: Optional[str]) -> str:
    safe = UNSAFE_CHARACTER.sub("-", (feature or "").lower()).lstrip(".-")
    return (safe or EMPTY_NAME)[: metrics_writer.NAME_LIMIT - STAMP_LENGTH]


def plugin_version() -> Optional[str]:
    code, text, _ = cli.version()
    found = json_object(text or "") if code == 0 else None
    return found.get("version") if found is not None and isinstance(found.get("version"), str) else None


def read_catalogue() -> Optional[Dict[str, Any]]:
    try:
        with open(CATALOGUE, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def writer_environment(parent: Optional[str]) -> Mapping[str, str]:
    return {**os.environ, metrics_writer.PARENT_VARIABLE: parent} if parent else dict(os.environ)


def start_fields(options: argparse.Namespace) -> Dict[str, Any]:
    return {
        "core": options.core,
        "feature": options.feature,
        "results": os.path.realpath(options.results) if options.results is not None else None,
        "retest": options.previous is not None,
        "final": bool(options.final),
        "spec": options.spec is not None,
    }


def present(warnings: Tuple[Optional[str], ...]) -> Tuple[str, ...]:
    return tuple(warning for warning in warnings if warning is not None)


def begun(root: Optional[str], options: Optional[argparse.Namespace]) -> Optional[Recording]:
    repo = repository_folder(root) if root is not None and options is not None else None
    if repo is None or options is None:
        return None
    start = datetime.datetime.now(datetime.timezone.utc)
    run = metrics_writer.run_id(run_name(options.feature), start)
    version = plugin_version()
    environ = writer_environment(options.parent)
    fields = start_fields(options)
    catalogue = read_catalogue()
    warnings = present(
        (
            metrics_writer.append_event(PLUGIN, version, repo, run, RUN_START, fields, environ=environ, now=start),
            metrics_writer.write_catalogue(PLUGIN, catalogue, environ=environ)
            if catalogue is not None
            else metrics_writer.WARNING_PREFIX + "catalogue: cannot read " + CATALOGUE,
        )
    )
    return Recording(repo, run, start, version, environ, fields, warnings)


def finished(recording: Optional[Recording], results: Optional[str], ending: Ending) -> Tuple[str, ...]:
    if recording is None:
        return ()
    end = datetime.datetime.now(datetime.timezone.utc)
    line = json_object(ending.line) or {}
    elapsed = round((end - recording.start).total_seconds(), SECONDS_DIGITS)
    end_fields = {"verdict": choice(line.get("verdict"), VERDICTS), "child_exit": ending.child_exit, "run_seconds": elapsed}
    ended = metrics_writer.append_event(
        PLUGIN, recording.plugin_version, recording.repo, recording.run, RUN_END, end_fields, environ=recording.environ, now=end
    )
    fields = summary_fields(recording, results, ending, line, end, elapsed)
    summarised = metrics_writer.write_summary(
        PLUGIN, recording.plugin_version, recording.repo, recording.run, fields, environ=recording.environ
    )
    return recording.warnings + present((ended, summarised))


def stamp(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.timezone.utc).strftime(TIME_FORMAT)


def choice(value: Any, allowed: Tuple[Any, ...]) -> Optional[Any]:
    return value if isinstance(value, str) and value in allowed else None


def text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def length(value: Any) -> Optional[int]:
    return len(value) if isinstance(value, list) else None


def seconds(minutes: Any) -> Optional[float]:
    return round(minutes * 60, SECONDS_DIGITS) if is_number(minutes) else None


def summary_reason(ending: Ending, line: Dict[str, Any]) -> Optional[str]:
    if ending.reason is not None:
        return ending.reason
    return text(line.get("reason")) if line.get("verdict") == "blocked" else None


def summary_fields(
    recording: Recording,
    results: Optional[str],
    ending: Ending,
    line: Dict[str, Any],
    end: datetime.datetime,
    elapsed: float,
) -> Dict[str, Any]:
    commits = verdict.recorded_commits(results) if results is not None else None
    findings = verdict.optional_json(os.path.join(results, verdict.FINDINGS)) if results is not None else None
    found = findings if isinstance(findings, dict) else {}
    fields = recording.start_fields
    return {
        "started": stamp(recording.start),
        "ended": stamp(end),
        "run_seconds": elapsed,
        "verdict": choice(line.get("verdict"), VERDICTS),
        "reason": summary_reason(ending, line),
        "core": fields["core"],
        "feature": fields["feature"],
        "core_commit": commits["core"] if commits is not None else None,
        "feature_commit": commits["feature"] if commits is not None else None,
        "retest": fields["retest"],
        "final": fields["final"],
        "spec": fields["spec"],
        "failures": length(line.get("failures")),
        "unproven": length(line.get("unproven")),
        "flaky": length(line.get("flaky")),
        "build": build_summary(found.get("build")),
        "suite": suite_summary(results) if results is not None else None,
        "paths": paths_summary(found.get("paths"), carried_names(results)),
        **recorded_spend(recording, results, end),
        "child_exit": ending.child_exit,
        "child_session": ending.child_session,
        "results": fields["results"],
        "spend_scope": OWN_SPEND,
        "imported": False,
    }


def build_summary(build: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(build, dict):
        return None
    return {"result": choice(build.get("result"), verdict.BUILD_RESULTS), "reason": text(build.get("reason"))}


def build_timings(entry: Any, phases: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict) or phases is None:
        return None
    return {
        "prepare_seconds": seconds(phases.get("prepare_minutes")),
        "suite_seconds": seconds(phases.get("suite_minutes")),
        "rerun_seconds": seconds(phases.get("rerun_minutes")),
        "reused": entry.get("reused") is True,
    }


def suite_summary(results: str) -> Optional[Dict[str, Any]]:
    suite = verdict.optional_json(os.path.join(results, verdict.SUITE))
    if not isinstance(suite, dict):
        return None
    minutes = verdict.recorded_suite(results) or {}
    return {
        "result": choice(suite.get("result"), SUITE_RESULTS),
        "reason": text(suite.get("reason")),
        "failures": length(suite.get("failures")),
        "pre_existing": length(suite.get("pre_existing")),
        "flaky": length(suite.get("flaky")),
        **{build: build_timings(suite.get(build), minutes.get(build)) for build in verdict.BUILDS},
    }


def carried_names(results: Optional[str]) -> Optional[FrozenSet[str]]:
    if results is None:
        return None
    path = os.path.join(results, verdict.RETEST)
    if not os.path.exists(path):
        return frozenset()
    plan = verdict.optional_json(path)
    carried = plan.get("carried_paths") if isinstance(plan, dict) else None
    if not isinstance(carried, list):
        return None
    return frozenset(entry["name"] for entry in carried if isinstance(entry, dict) and isinstance(entry.get("name"), str))


def path_summary(path: Dict[str, Any], carried: Optional[FrozenSet[str]]) -> Dict[str, Any]:
    check = path.get("check")
    name = text(path.get("name"))
    return {
        "name": name,
        "kind": choice(path.get("kind"), verdict.PATH_KINDS),
        "status": choice(path.get("status"), verdict.PATH_STATUSES),
        "check": choice(check.get("kind"), verdict.CHECK_KINDS) if isinstance(check, dict) else None,
        "retry": choice(path.get("retry"), RETRY_OUTCOMES),
        "carried": name in carried if carried is not None and name is not None else None,
    }


def paths_summary(paths: Any, carried: Optional[FrozenSet[str]]) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(paths, list):
        return None
    return [path_summary(path, carried) for path in paths if isinstance(path, dict)]


def caller_transcript(session: str) -> Optional[str]:
    base = spend.claude_projects()
    found = [os.path.join(base, name, session + ".jsonl") for name in spend.listed(base)]
    return next((path for path in found if os.path.isfile(path)), None)


def results_transcripts(results: Optional[str]) -> List[spend.Transcript]:
    if results is None:
        return []
    scope = argparse.Namespace(results=results, transcripts=None, origin=None)
    _, transcripts = spend.scoped_transcripts(scope)
    return transcripts


def within(transcript: spend.Transcript, end: datetime.datetime) -> spend.Transcript:
    return transcript._replace(rows=[row for row in transcript.rows if row.timestamp <= end])


def price_table() -> spend.PriceTable:
    try:
        return spend.read_prices(spend.PRICES)
    except Refusal:
        return spend.PriceTable(None, {})


def mark_lines(results: Optional[str]) -> Optional[List[spend.MarkLine]]:
    path = os.path.join(results, mark.MARKS) if results is not None else None
    if path is None or not os.path.lexists(path):
        return []
    if not (os.path.isfile(path) and os.access(path, os.R_OK)):
        return None
    try:
        return spend.read_mark_lines(results)
    except (Refusal, OSError, ValueError):
        return None


def kinds(counted: Dict[str, Any]) -> Dict[str, int]:
    return {kind: counted[kind] for kind in spend.KINDS}


def spent(counted: Dict[str, Any]) -> Dict[str, Any]:
    return {"usd": counted["dollars"], "tokens": kinds(counted)}


def group_rows(groups: List[Dict[str, Any]], label: str) -> List[Dict[str, Any]]:
    return [
        {
            label: group["name"],
            "build": choice(group["build"], verdict.BUILDS),
            "elapsed_seconds": seconds(group["minutes"]),
            **spent(group),
        }
        for group in groups
    ]


def caller_summary(caller: Optional[spend.Transcript], start: datetime.datetime, prices: spend.Prices) -> Dict[str, Any]:
    report = spend.spend_report([caller] if caller is not None else [], start, prices, [])
    return {**spent(report), "messages": report["messages"]}


def recorded_spend(recording: Recording, results: Optional[str], end: datetime.datetime) -> Dict[str, Any]:
    try:
        return spend_summary(recording, results, end)
    except (Refusal, OSError, ValueError):
        return dict.fromkeys(SPEND_FIELDS)


def spend_summary(recording: Recording, results: Optional[str], end: datetime.datetime) -> Dict[str, Any]:
    session = recording.environ.get(metrics_writer.SESSION_VARIABLE) or None
    located = caller_transcript(session) if session is not None else None
    caller = within(spend.read_transcript(located), end) if located is not None else None
    missing = session is not None and caller is None
    prices = price_table()
    marked = mark_lines(results)
    transcripts = results_transcripts(results) + ([caller] if caller is not None else [])
    report = spend.spend_report(transcripts, recording.start, prices.rates, marked or [])
    waiting = report["waiting"]
    return {
        "usd": None if missing else report["dollars"],
        "price_date": prices.date,
        "tokens": kinds(report),
        "messages": report["messages"],
        "models": [{"model": model, "tokens": kinds(entry), "usd": entry["dollars"]} for model, entry in report["models"].items()],
        "unpriced": report["unpriced"],
        "steps": group_rows(report["steps"], "step") if marked is not None else None,
        "drives": group_rows(report["paths"], "path") if marked is not None else None,
        "shared": spent(report["shared"]) if marked is not None else None,
        "caller": None if missing else caller_summary(caller, recording.start, prices.rates),
        "waiting": {
            "person_seconds": seconds(waiting[spend.PERSON]),
            "tool_seconds": seconds(waiting[spend.TOOL]),
            "model_seconds": seconds(waiting[spend.MODEL]),
        },
        "expired_rewrites": {"count": report["expired_rewrites"]["count"], "cache_write": report["expired_rewrites"]["tokens"]},
    }
