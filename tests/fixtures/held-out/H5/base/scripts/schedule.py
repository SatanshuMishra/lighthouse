import sys

import glaze_table

USAGE = "usage: schedule.py GLAZE"


def schedule_lines(glaze):
    header = "{} fires to cone {}".format(glaze["name"], glaze["cone"])
    steps = [
        "{}. {} C/h to {} C, hold {} min".format(number, rate, target, hold)
        for number, (rate, target, hold) in enumerate(glaze["segments"], start=1)
    ]
    return [header] + steps


def main(argv):
    if len(argv) != 1:
        print(USAGE, file=sys.stderr)
        return 2
    glaze = glaze_table.find(argv[0])
    if glaze is None:
        print("no firing schedule for {}".format(argv[0].strip()), file=sys.stderr)
        return 1
    print("\n".join(schedule_lines(glaze)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
