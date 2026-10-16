#!/bin/sh
set -u
KILNROOM_TOKEN=probe-studio-token
export KILNROOM_TOKEN
python3 - <<'PY'
import http.client
import json
import os
import subprocess
import sys

server = subprocess.Popen(
    [sys.executable, "-m", "kilnroom", "--host", "127.0.0.1", "--port", "0"],
    stdout=subprocess.PIPE,
    text=True,
)


def call(port, method, path, body=None, token=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        credentials = {"Authorization": "Bearer " + token} if token else {}
        connection.request(method, path, body=None if body is None else json.dumps(body), headers={**headers, **credentials})
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8") or "{}")
    finally:
        connection.close()


def verdict(port):
    token = os.environ["KILNROOM_TOKEN"]
    queued, _ = call(port, "POST", "/pieces", {"maker": "Probe", "title": "Test tile"})
    if queued != 401:
        return 2, "POST /pieces without a token answered {}, expected 401".format(queued)
    withdrawn, _ = call(port, "DELETE", "/pieces/1")
    _, listing = call(port, "GET", "/pieces")
    ids = [piece["id"] for piece in listing["pieces"]]
    if withdrawn != 401 or 1 not in ids:
        return 1, "DELETE /pieces/1 without a token answered {} and the queue now holds {}".format(withdrawn, ids)
    allowed, _ = call(port, "DELETE", "/pieces/1", token=token)
    _, listing = call(port, "GET", "/pieces")
    ids = [piece["id"] for piece in listing["pieces"]]
    if allowed != 200 or 1 in ids:
        return 1, "DELETE /pieces/1 with the studio token answered {} and the queue holds {}".format(allowed, ids)
    return 0, "changes without a token answer 401, and DELETE with the studio token withdraws the piece"


try:
    first = server.stdout.readline().strip()
    if not first.startswith("kilnroom listening on http://"):
        print("probe: the server did not start: {}".format(first))
        sys.exit(2)
    code, message = verdict(int(first.rsplit(":", 1)[1]))
    print("probe: " + message)
    sys.exit(code)
finally:
    server.terminate()
    server.wait(timeout=10)
PY
