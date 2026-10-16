import argparse
import sys

from milepost import trips


def log_trip(args):
    path = trips.data_path()
    try:
        entry = trips.trip(args.date, args.place, args.km)
    except ValueError:
        print("milepost: {} is not a date in the form YYYY-MM-DD".format(args.date), file=sys.stderr)
        return 2
    trips.save(path, trips.load(path) + [entry])
    print("Logged {} {} {:.1f} km".format(entry["date"], entry["place"], entry["km"]))
    return 0


def show_trips(args):
    listed = trips.numbered(trips.load(trips.data_path()))
    if not listed:
        print("No trips logged.")
    for number, entry in listed:
        print(trips.describe(number, entry))
    return 0


def total_distance(args):
    logged = trips.load(trips.data_path())
    print("Total: {:.1f} km over {} trips".format(sum(entry["km"] for entry in logged), len(logged)))
    return 0


def drop_trip(args):
    path = trips.data_path()
    logged = trips.load(path)
    chosen = dict(trips.numbered(logged)).get(args.number)
    if chosen is None:
        print("milepost: no trip is numbered {}".format(args.number), file=sys.stderr)
        return 1
    trips.save(path, [entry for entry in logged if entry is not chosen])
    print("Dropped {}".format(trips.describe(args.number, chosen)))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="milepost", description="Log car journeys for mileage claims.")
    commands = parser.add_subparsers(dest="command", required=True)
    log = commands.add_parser("log", help="record one trip")
    log.add_argument("date", help="the day of the trip, as YYYY-MM-DD")
    log.add_argument("place", help="where you drove to")
    log.add_argument("km", type=float, help="the distance driven, in kilometres")
    log.set_defaults(handler=log_trip)
    commands.add_parser("show", help="print every trip with its number").set_defaults(handler=show_trips)
    commands.add_parser("total", help="add up the distance of every trip").set_defaults(handler=total_distance)
    drop = commands.add_parser("drop", help="remove one trip by the number show prints")
    drop.add_argument("number", type=int, help="the trip's number in show")
    drop.set_defaults(handler=drop_trip)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.handler(args)
