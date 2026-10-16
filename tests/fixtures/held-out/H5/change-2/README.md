# kilnmate

A Claude Code plugin for studio potters.

## Skills

- `firing-schedule` gives the cone and the ramp, hold and cooling segments for a glaze, read from the studio table in `data/glazes.json` through `scripts/schedule.py`.
- `firing-log` records a kiln firing of a glaze in the potter's firing log.
- `glaze-faults` names the likely cause of a glaze defect after firing and one change to try next time.

## Scripts

`python3 scripts/schedule.py "Floating Blue"` prints the glaze's cone and one numbered line per segment: rate in degrees Celsius per hour, target temperature and hold in minutes. With `--json` it prints the same schedule as one JSON object.

`python3 scripts/schedule.py --json "Floating Blue" | python3 scripts/log_firing.py` appends the firing to the log at `KILNMATE_LOG`, or `~/.kilnmate/firings.jsonl` when it is unset, and prints the firing's number.

## Tests

```
python3 -m unittest discover -s tests
```
