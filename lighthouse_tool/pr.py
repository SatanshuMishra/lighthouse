import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from lighthouse_tool import change
from lighthouse_tool import repo as repository
from lighthouse_tool.repo import Parser, Refusal
from lighthouse_tool import verdict as verdicts

OPENS_WITHOUT_FINAL = ("green", "unproven")
TITLE_LIMIT = 72
TYPE_FORM = re.compile(r"[a-z]+\Z")
SCOPE_FORM = re.compile(r"[a-z0-9-]+\Z")
SCOPE_OUTSIDER = re.compile(r"[^a-z0-9-]")
SUMMARY_FORM = re.compile(r"[a-z][^\r\n]*\Z")


def parser() -> Parser:
    arguments = Parser(prog="lighthouse pr", add_help=False)
    arguments.add_argument("--repo", required=True)
    arguments.add_argument("--core", required=True)
    arguments.add_argument("--feature", required=True)
    arguments.add_argument("--results", required=True)
    arguments.add_argument("--summary", required=True)
    arguments.add_argument("--type", dest="change_type", default="feat")
    arguments.add_argument("--scope")
    arguments.add_argument("--why")
    arguments.add_argument("--final", action="store_true")
    return arguments


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        results = os.path.realpath(options.results)
        line = read_verdict(results)
        findings = verdicts.read_findings(results)
        if line["verdict"] not in OPENS_WITHOUT_FINAL and not options.final:
            return 1, None, "lighthouse pr: the verdict is {}, which needs --final to open the pull request".format(
                line["verdict"]
            )
        pull_request_title = title(options.change_type, scope_of(options.repo, options.scope), options.summary)
        changes = change.change_set(options.repo, options.core, options.feature)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse pr: {}".format(refusal)
    return 0, json.dumps(
        {
            "title": pull_request_title,
            "body": body(options, changes, findings, line),
            "base": options.core,
            "head": options.feature,
            "draft": line["verdict"] != "green",
        }
    ), None


def read_verdict(results: str) -> Dict[str, Any]:
    path = os.path.join(results, verdicts.VERDICT)
    try:
        with open(path, encoding="utf-8") as handle:
            line = json.load(handle)
    except OSError as error:
        raise Refusal("{} cannot be read: {}".format(path, error.strerror or error))
    except ValueError:
        raise Refusal("{} is not JSON".format(path))
    if not isinstance(line, dict) or line.get("verdict") not in verdicts.VERDICTS:
        raise Refusal("{} carries no verdict of {}".format(path, ", ".join(verdicts.VERDICTS)))
    for key in ("failures", "unproven", "flaky"):
        if not isinstance(line.get(key), list):
            raise Refusal("{} in {} must be a list".format(key, path))
    return line


def scope_of(repo: str, scope: Optional[str]) -> str:
    if scope is not None:
        return scope
    folder = repository.repository_folder(repo)
    if folder is None:
        raise Refusal("{} is not a git repository".format(repo))
    return SCOPE_OUTSIDER.sub("-", folder.lower())


def title(change_type: str, scope: str, summary: str) -> str:
    if not TYPE_FORM.match(change_type):
        raise Refusal("the type {!r} must be lowercase letters".format(change_type))
    if not SCOPE_FORM.match(scope):
        raise Refusal("the scope {!r} must be lowercase letters, digits and -".format(scope))
    if not SUMMARY_FORM.match(summary):
        raise Refusal("the summary {!r} must be one line starting with a lowercase letter".format(summary))
    composed = "{}({}): {}".format(change_type, scope, summary)
    if len(composed) > TITLE_LIMIT:
        raise Refusal("the title is {} characters, more than {}: {}".format(len(composed), TITLE_LIMIT, composed))
    return composed


def what_changed(changes: Dict[str, Any]) -> List[str]:
    pull_requests = changes["pull_requests"]
    if pull_requests:
        return verdicts.bullets(["{} (#{})".format(entry["title"], entry["number"]) for entry in pull_requests], "None.")
    return verdicts.bullets([commit["subject"] for commit in changes["commits"]], "None.")


def risk(line: Dict[str, Any]) -> List[str]:
    items = (
        ["Unresolved: {}".format(name) for name in line["failures"]]
        + ["Unproven: {}".format(name) for name in line["unproven"]]
        + ["Flaky: {}".format(name) for name in line["flaky"]]
    )
    return ["Verdict: {}".format(line["verdict"]), ""] + verdicts.bullets(items, "None found.")


def suite_line(suite: Dict[str, Any]) -> str:
    return "Suite: {}, {} failures, {} pre-existing{}".format(
        suite["result"],
        len(suite["failures"]),
        len(suite["pre_existing"]),
        "; " + suite["reason"] if suite["reason"] else "",
    )


def path_line(path: Dict[str, Any]) -> str:
    return "{}: {}, {}; evidence: {}".format(
        path["name"],
        path["kind"],
        path["status"],
        ", ".join(path["evidence"]) if path["evidence"] else "none",
    )


def rechecked(paths: List[Dict[str, Any]]) -> str:
    names = [path["name"] for path in paths if path["kind"] == "neighbour" and path["status"] != "unproven"]
    return "Neighbours rechecked: {}".format(", ".join(names) if names else "none.")


def verification(findings: Dict[str, Any]) -> List[str]:
    paths = findings["paths"]
    spend = findings["spend"]
    return (
        [suite_line(findings["suite"]), ""]
        + verdicts.bullets([path_line(path) for path in paths], "No product paths.")
        + ["", rechecked(paths), "", "lighthouse spent {} tokens over {} minutes.".format(spend["tokens"], spend["minutes"])]
    )


def links(changes: Dict[str, Any]) -> List[str]:
    return verdicts.bullets([entry["url"] for entry in changes["pull_requests"] if entry.get("url")], "None.")


def body(options: argparse.Namespace, changes: Dict[str, Any], findings: Dict[str, Any], line: Dict[str, Any]) -> str:
    lines = (
        verdicts.section("What changed", what_changed(changes))
        + verdicts.section("Why", [options.why or "Carries {} into {}.".format(options.feature, options.core)])
        + verdicts.section("Risk", risk(line))
        + verdicts.section("Verification", verification(findings))
        + verdicts.section("Links", links(changes))
    )
    return "\n".join(lines).rstrip("\n") + "\n"
