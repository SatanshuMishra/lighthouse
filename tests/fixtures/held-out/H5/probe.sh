#!/bin/sh
python3 - <<'PY'
import json
import os
import subprocess
import sys
import tempfile

glazes = ["Floating Blue", "Oribe Green"]
with tempfile.TemporaryDirectory() as folder:
    log = os.path.join(folder, "firings.jsonl")
    env = {**os.environ, "KILNMATE_LOG": log}
    runs = []
    for glaze in glazes:
        schedule = subprocess.run(
            [sys.executable, "scripts/schedule.py", "--json", glaze], env=env, capture_output=True, text=True
        )
        logged = subprocess.run(
            [sys.executable, "scripts/log_firing.py"], input=schedule.stdout, env=env, capture_output=True, text=True
        )
        runs.append((glaze, schedule.returncode, logged.returncode, logged.stdout + logged.stderr))
    failed = [run for run in runs if run[1] != 0 or run[2] != 0]
    if failed:
        print("firing-log did not log {}".format(failed))
        sys.exit(1)
    with open(log, encoding="utf-8") as handle:
        entries = [json.loads(line) for line in handle if line.strip()]
    names = [entry["glaze"] for entry in entries]
    if names != glazes:
        print("firing log holds {} where {} was expected".format(names, glazes))
        sys.exit(1)
print("firing-log logged every glaze, in the table or not")
PY
