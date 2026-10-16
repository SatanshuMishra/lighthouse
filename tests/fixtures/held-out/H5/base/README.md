# kilnmate

A Claude Code plugin for studio potters.

## Skills

- `firing-schedule` gives the cone and the ramp, hold and cooling segments for a glaze, read from the studio table in `data/glazes.json` through `scripts/schedule.py`.
- `glaze-faults` names the likely cause of a glaze defect after firing and one change to try next time.

## Scripts

`python3 scripts/schedule.py "Floating Blue"` prints the glaze's cone and one numbered line per segment: rate in degrees Celsius per hour, target temperature and hold in minutes.

## Tests

```
python3 -m unittest discover -s tests
```
