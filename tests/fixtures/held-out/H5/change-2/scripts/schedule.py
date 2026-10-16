import json
import sys

import glaze_table

USAGE = "usage: schedule.py [--json] GLAZE"


def schedule_lines(glaze):
    header = "{} fires to cone {}".format(glaze["name"], glaze["cone"])
    steps = [
        "{}. {} C/h to {} C, hold {} min".format(number, rate, target, hold)
        for number, (rate, target, hold) in enumerate(glaze["segments"], start=1)
    ]
    return [header] + steps


def schedule_record(glaze):
    return {
        "glaze": glaze["name"],
        "cone": glaze["cone"],
        "segments": [
            {"rate": rate, "target": target, "hold": hold} for rate, target, hold in glaze["segments"]
        ],
    }


def main(argv):
    as_json = argv[:1] == ["--json"]
    names = argv[1:] if as_json else argv
    if len(names) != 1:
        print(USAGE, file=sys.stderr)
        return 2
    glaze = glaze_table.find(names[0])
    if glaze is None:
        print("no firing schedule for {}".format(names[0].strip()), file=sys.stderr)
        return 1
    print(json.dumps(schedule_record(glaze)) if as_json else "\n".join(schedule_lines(glaze)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
