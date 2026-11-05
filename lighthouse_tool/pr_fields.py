import json
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool import handoff, noninteractive
from lighthouse_tool.records import write_atomically
from lighthouse_tool.repo import Refusal

H15 = "h15-pr-fields"
H16 = "h16-pr-render"
FIELDS = "pr-fields.json"
RENDER_PROGRAM = "pull-request"
RENDER = "pull-request render"
COMPOSER = "lighthouse pr"
DRAFT_KEYS = ("problem", "change", "impact", "approach", "tradeoffs")
FIELD_ORDER = ("problem", "change", "approach", "impact", "tradeoffs")
UNRESOLVED_KEYS = ("failures", "unproven", "flaky")
SCOPE_OUTSIDER = re.compile(r"[^a-z0-9-]")
SCOPE_LENGTH = 16
TABLE_HEAD = ("| Check | Result |", "|---|---|")


def read_draft(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise Refusal("the fields draft {} cannot be read: {}".format(path, error.strerror or error))
    try:
        draft = json.loads(text)
    except ValueError:
        raise Refusal("the fields draft {} is not JSON".format(path))
    if not isinstance(draft, dict):
        raise Refusal("the fields draft {} is not a JSON object".format(path))
    unknown = sorted(key for key in draft if key not in DRAFT_KEYS)
    if unknown:
        raise Refusal(
            "the fields draft {} may hold only {}; it also holds {}".format(
                path, ", ".join(DRAFT_KEYS), ", ".join(unknown)
            )
        )
    return draft


def scope_from_folder(folder: str) -> str:
    kept = SCOPE_OUTSIDER.sub("", folder.lower()).lstrip("-")
    return kept[:SCOPE_LENGTH].rstrip("-")


def compose_title(change_type: str, scope: str, summary: str) -> str:
    if scope:
        return "{}({}): {}".format(change_type, scope, summary)
    return "{}: {}".format(change_type, summary)


def testing_rows(line: Dict[str, Any], findings: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"check": "Lighthouse verdict", "result": str(line["verdict"])},
        {"check": "Project suite", "result": str(findings["suite"]["result"])},
        {"check": "Failures", "result": str(len(line["failures"]))},
        {"check": "Unproven", "result": str(len(line["unproven"]))},
        {"check": "Flaky", "result": str(len(line["flaky"]))},
    ]


def build_fields(title: str, draft: Dict[str, Any], rows: List[Dict[str, str]]) -> Dict[str, Any]:
    drafted = {key: draft[key] for key in FIELD_ORDER if key in draft}
    return {"title": title, **drafted, "testing": rows}


def unresolved_names(line: Dict[str, Any]) -> List[str]:
    names = [name for key in UNRESOLVED_KEYS for name in line[key]]
    return [name for index, name in enumerate(names) if name not in names[:index]]


def missing_names(line: Dict[str, Any], fields: Dict[str, Any]) -> List[str]:
    sentences = fields.get("tradeoffs", [])
    return [name for name in unresolved_names(line) if not any(name in sentence for sentence in sentences)]


def refuse_missing_names(line: Dict[str, Any], fields: Dict[str, Any], draft_path: str) -> None:
    missing = missing_names(line, fields)
    if missing:
        raise Refusal(
            "every failures, unproven and flaky name of verdict.json must appear in a tradeoffs sentence of the fields draft {}; missing: {}".format(
                draft_path, ", ".join(missing)
            )
        )


def checked_fields(target: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    return handoff.check_before_writing(target, H15, fields)


def write_fields(target: str, fields: Dict[str, Any]) -> str:
    try:
        write_atomically(target, json.dumps(fields, indent=2) + "\n")
    except OSError as error:
        raise Refusal("cannot write {}: {}".format(target, error.strerror or error))
    return target


def written_fields(results: str, draft_path: str, line: Dict[str, Any], fields: Dict[str, Any]) -> str:
    target = os.path.join(results, FIELDS)
    checked = checked_fields(target, fields)
    refuse_missing_names(line, checked, draft_path)
    return write_fields(target, checked)


def render_program() -> Optional[str]:
    return shutil.which(RENDER_PROGRAM)


def render_environment() -> Dict[str, str]:
    try:
        return noninteractive.environment(os.environ)
    except noninteractive.UnusableEnvironment as error:
        raise Refusal("{} cannot be started: {}".format(RENDER, error))


def run_render(program: str, fields_path: str) -> Tuple[int, str, str]:
    try:
        completed = subprocess.run(
            [program, "render", "--fields", fields_path],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=render_environment(),
        )
    except OSError as error:
        raise Refusal("{} cannot be started: {}".format(RENDER, error.strerror or error))
    return completed.returncode, completed.stdout, completed.stderr


def rendered_line(code: int, stdout: str, stderr: str) -> Any:
    if code != 0:
        reason = stderr.strip().splitlines()[-1] if stderr.strip() else "no message"
        raise Refusal("{} exited {}: {}".format(RENDER, code, reason))
    lines = [text for text in stdout.splitlines() if text.strip()]
    if len(lines) != 1:
        raise Refusal("{} printed {} lines where {} needs one JSON line".format(RENDER, len(lines), handoff.schema_file(H16)))
    try:
        return json.loads(lines[0])
    except ValueError:
        raise Refusal("{} printed a line that is not JSON, so it cannot meet {}".format(RENDER, handoff.schema_file(H16)))


def rendered(program: str, fields_path: str) -> Dict[str, str]:
    value = rendered_line(*run_render(program, fields_path))
    checked = handoff.read_through(RENDER, "the output of " + RENDER, H16, value)
    return {"title": checked["title"], "body": checked["body"]}


def joined_sentences(sentences: List[str]) -> str:
    return " ".join(sentences)


def bullets(sentences: List[str]) -> List[str]:
    return ["- " + sentence for sentence in sentences]


def change_section(fields: Dict[str, Any]) -> str:
    listed = "\n".join(["## Change", *bullets(fields["change"])])
    approach = fields.get("approach", [])
    return listed + "\n\n" + joined_sentences(approach) if approach else listed


def tradeoffs_sections(fields: Dict[str, Any]) -> List[str]:
    tradeoffs = fields.get("tradeoffs", [])
    if not tradeoffs:
        return []
    return ["\n".join(["## Trade-offs and open problems", *bullets(tradeoffs)])]


def testing_section(fields: Dict[str, Any]) -> str:
    rows = ["| {} | {} |".format(row["check"], row["result"]) for row in fields["testing"]]
    return "\n".join(["## Testing", *TABLE_HEAD, *rows])


def composed_body(fields: Dict[str, Any]) -> str:
    sections = [
        "## Problem\n" + joined_sentences(fields["problem"]),
        change_section(fields),
        "## Impact\n" + joined_sentences(fields["impact"]),
        *tradeoffs_sections(fields),
        testing_section(fields),
    ]
    return "\n\n".join(sections)


def composed(fields: Dict[str, Any]) -> Dict[str, str]:
    value = {"title": fields["title"], "body": composed_body(fields)}
    return handoff.read_through(COMPOSER, "the title and body " + COMPOSER + " composed", H16, value)


def pull_request(fields_path: str, fields: Dict[str, Any]) -> Dict[str, str]:
    program = render_program()
    if program is None:
        return composed(fields)
    return rendered(program, fields_path)
