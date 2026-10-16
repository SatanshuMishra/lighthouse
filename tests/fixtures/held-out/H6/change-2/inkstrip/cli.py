import argparse
import re
import sys

from inkstrip import layout, printer


def show_preview(args, open_printer):
    print("\n".join(layout.framed(layout.lay_out(args.rows))))
    return 0


def print_one(args, open_printer):
    lines = layout.lay_out(args.rows)
    print(printer.print_label(open_printer(), lines))
    return 0


def feed_one(args, open_printer):
    print(printer.feed(open_printer()))
    return 0


def read_sheet(handle):
    blocks = re.split(r"\n[ \t]*\n", handle.read())
    return tuple(layout.lay_out(block.splitlines()) for block in blocks if block.strip())


def print_sheet(args, open_printer):
    with args.file as handle:
        labels = read_sheet(handle)
    link = open_printer()
    for lines in labels:
        printer.print_label(link, lines)
        printer.feed(link)
    print("printed {} labels".format(len(labels)))
    return 0


def report_status(args, open_printer):
    print(open_printer().transmit("STATUS?"))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="inkstrip")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preview = subparsers.add_parser("preview", help="show how a label will be laid out, without a printer")
    preview.add_argument("rows", nargs="+", metavar="ROW")
    preview.set_defaults(handler=show_preview)
    single = subparsers.add_parser("print", help="print one label onto the blank label under the print head")
    single.add_argument("rows", nargs="+", metavar="ROW")
    single.set_defaults(handler=print_one)
    advance = subparsers.add_parser("feed", help="advance the strip by one label")
    advance.set_defaults(handler=feed_one)
    batch = subparsers.add_parser("sheet", help="print every label in a file, one per label, in one run")
    batch.add_argument("file", type=argparse.FileType("r", encoding="utf-8"), metavar="FILE")
    batch.set_defaults(handler=print_sheet)
    status = subparsers.add_parser("status", help="print what the label printer reports")
    status.set_defaults(handler=report_status)
    return parser


def main(argv=None, open_printer=printer.open_printer):
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args, open_printer)
    except layout.LabelError as error:
        print("inkstrip: {}".format(error), file=sys.stderr)
        return 2
    except printer.PrinterUnavailable as error:
        print("inkstrip: {}".format(error), file=sys.stderr)
        return 3
