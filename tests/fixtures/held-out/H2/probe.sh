#!/bin/sh
set -eu
exec python3 - <<'PROBE'
import base64
import hashlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
STYLESHEET = re.compile(r"<link\b[^>]*\brel=\"stylesheet\"[^>]*>", re.I)
ATTRIBUTE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*\"([^\"]*)\"")
HANDLER = re.compile(r"<[a-zA-Z][^>]*\s(on[a-z]+)\s*=", re.I)
ADDRESS = re.compile(r"http://\S+")


def attributes(text):
    return {name.lower(): value for name, value in ATTRIBUTE.findall(text)}


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.headers, ""


def normalised(source):
    return source if source.lower().startswith(("'nonce-", "'sha")) else source.lower()


def directives(policy):
    parts = [part.split() for part in policy.split(";") if part.strip()]
    return {part[0].lower(): [normalised(source) for source in part[1:]] for part in reversed(parts)}


def script_sources(policy):
    found = directives(policy)
    return next((found[name] for name in ("script-src-elem", "script-src", "default-src") if name in found), None)


def handler_sources(policy):
    found = directives(policy)
    return next((found[name] for name in ("script-src-attr", "script-src", "default-src") if name in found), None)


def digest(text):
    return "'sha256-{}'".format(base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii"))


def keyed(sources):
    return any(source.startswith(("'nonce-", "'sha256-", "'sha384-", "'sha512-")) for source in sources)


def inline_allowed(sources, nonce, body):
    if sources is None:
        return True
    if nonce and "'nonce-{}'".format(nonce) in sources:
        return True
    if digest(body) in sources:
        return True
    return "'unsafe-inline'" in sources and not keyed(sources)


def handler_allowed(sources):
    return sources is None or ("'unsafe-inline'" in sources and not keyed(sources))


def same_origin_allowed(sources):
    return sources is None or "'self'" in sources or "*" in sources


def blocked_scripts(policies, page):
    found = [(attributes(opening), body) for opening, body in SCRIPT.findall(page)]
    inline = [
        "an inline script of {} characters".format(len(body.strip()))
        for fields, body in found
        if "src" not in fields and body.strip()
        and not all(inline_allowed(script_sources(policy), fields.get("nonce"), body) for policy in policies)
    ]
    external = [
        "the script {}".format(fields["src"])
        for fields, _ in found
        if "src" in fields and not all(same_origin_allowed(script_sources(policy)) for policy in policies)
    ]
    handlers = [
        "the {} attribute".format(name)
        for name in HANDLER.findall(page)
        if not all(handler_allowed(handler_sources(policy)) for policy in policies)
    ]
    return inline + external + handlers


def missing_resources(address, page):
    scripts = [attributes(opening).get("src") for opening, _ in SCRIPT.findall(page)]
    stylesheets = [attributes(link).get("href", "") for link in STYLESHEET.findall(page)]
    paths = [path for path in scripts if path is not None] + stylesheets
    statuses = [(path, fetch(urllib.parse.urljoin(address, path))[0]) for path in paths]
    return ["{} answered {}".format(path, status) for path, status in statuses if status != 200]


def check(address):
    status, headers, page = fetch(address)
    if status != 200:
        return ["the page answered {}".format(status)]
    policies = headers.get_all("Content-Security-Policy") or []
    blocked = ["the browser refuses {}".format(item) for item in blocked_scripts(policies, page)]
    return blocked + missing_resources(address, page)


def main():
    server = subprocess.Popen(
        [sys.executable, "serve.py", "--port", "0"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        match = ADDRESS.search(server.stdout.readline())
        if match is None:
            print("serve.py printed no address")
            return 2
        problems = check(match.group(0))
    finally:
        server.terminate()
        server.wait(timeout=10)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


sys.exit(main())
PROBE
