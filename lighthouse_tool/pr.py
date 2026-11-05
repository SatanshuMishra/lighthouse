import json
import os
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool import handoff, pr_fields
from lighthouse_tool import repo as repository
from lighthouse_tool.change import MissingBranch
from lighthouse_tool.repo import Parser, Refusal
from lighthouse_tool import verdict as verdicts

Outcome = Tuple[int, Optional[str], Optional[str]]

OPENS_WITHOUT_FINAL = ("green", "unproven")
READY_VERDICT = "green"
VERDICT_PRODUCER = "lighthouse verdict"


def parser() -> Parser:
    arguments = Parser(prog="lighthouse pr", add_help=False)
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--core", required=True)
    arguments.add_argument("--feature", required=True)
    arguments.add_argument("--results", required=True)
    arguments.add_argument("--summary", required=True)
    arguments.add_argument("--type", dest="change_type", default="feat")
    arguments.add_argument("--scope")
    arguments.add_argument("--draft-fields", dest="draft_fields", required=True)
    arguments.add_argument("--final", action="store_true")
    return arguments


def run(argv: List[str]) -> Outcome:
    try:
        options = parser().parse_args(argv[1:])
        results = os.path.realpath(options.results)
        line = read_verdict(results)
        findings = verdicts.read_findings(results)
        if line["verdict"] not in OPENS_WITHOUT_FINAL and not options.final:
            return 1, None, "lighthouse pr: the verdict is {}, which needs --final to open the pull request".format(
                line["verdict"]
            )
        root = checked_branches(options.repo, options.core, options.feature)
        title = pr_fields.compose_title(options.change_type, scope_of(root, options.scope), options.summary)
        draft = pr_fields.read_draft(options.draft_fields)
        fields = pr_fields.build_fields(title, draft, pr_fields.testing_rows(line, findings))
        fields_path = pr_fields.written_fields(results, options.draft_fields, line, fields)
        shown = pr_fields.pull_request(fields_path, fields)
    except handoff.FormatRefusal as refusal:
        printed = {"error": str(refusal), "schema": refusal.schema, "errors": list(refusal.errors)}
        return 2, json.dumps(printed), "lighthouse pr: {}".format(refusal)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse pr: {}".format(refusal)
    return 0, json.dumps(
        {
            "title": shown["title"],
            "body": shown["body"],
            "base": options.core,
            "head": options.feature,
            "draft": line["verdict"] != READY_VERDICT,
        }
    ), None


def read_verdict(results: str) -> Dict[str, Any]:
    path = os.path.join(results, verdicts.VERDICT)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise Refusal("{} cannot be read: {}".format(path, error.strerror or error))
    try:
        line = json.loads(text)
    except ValueError:
        raise Refusal("{} is not JSON".format(path))
    checked = handoff.read_through(VERDICT_PRODUCER, verdicts.VERDICT, verdicts.H13, line)
    if "verdict" not in checked:
        raise Refusal("{} holds a refusal, not a verdict line".format(path))
    return checked


def checked_branches(repo: str, core: str, feature: str) -> str:
    root = repository.require_root(repo)
    for branch in (core, feature):
        if repository.resolve_branch(root, branch) is None:
            raise MissingBranch(branch)
    return root


def scope_of(root: str, scope: Optional[str]) -> str:
    if scope is not None:
        return scope
    folder = repository.repository_folder(root)
    if folder is None:
        raise Refusal("{} is not a git repository".format(root))
    return pr_fields.scope_from_folder(folder)
