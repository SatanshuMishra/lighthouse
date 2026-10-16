import argparse
import sys

from hearthctl import boost, device, schedule


def show_status(args, connect):
    print(connect().send("TEMP?"))
    return 0


def set_target(args, connect):
    print(connect().send("SET {:.1f}".format(args.celsius)))
    return 0


def show_plan(args, connect):
    for start, celsius in schedule.programme(args.entries):
        print("{} {:.1f}".format(start, celsius))
    return 0


def start_boost(args, connect):
    print(boost.start(connect()))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="hearthctl")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="print the room temperature the thermostat reads")
    status.set_defaults(handler=show_status)
    target = subparsers.add_parser("set", help="change the thermostat's target temperature")
    target.add_argument("celsius", type=float)
    target.set_defaults(handler=set_target)
    plan = subparsers.add_parser("plan", help="print a day's heating programme in time order")
    plan.add_argument("entries", nargs="+", metavar="HH:MM=CELSIUS")
    plan.set_defaults(handler=show_plan)
    heat = subparsers.add_parser("boost", help="heat at full power for 30 minutes, then return to the programme")
    heat.set_defaults(handler=start_boost)
    return parser


def main(argv=None, connect=device.connect):
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args, connect)
    except device.DeviceUnavailable as error:
        print("hearthctl: {}".format(error), file=sys.stderr)
        return 3
