from jotbook import notes, paths

NAME = "list"


def register(subparsers, shared):
    parser = subparsers.add_parser(NAME, parents=[shared], help="print every note, numbered")
    parser.set_defaults(handler=run)


def run(args):
    for number, text in enumerate(notes.load(paths.notes_file(args, "store")), start=1):
        print("{}. {}".format(number, text))
    return 0
