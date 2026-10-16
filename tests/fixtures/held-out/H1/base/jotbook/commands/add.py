from jotbook import notes, paths

NAME = "add"


def register(subparsers, shared):
    parser = subparsers.add_parser(NAME, parents=[shared], help="add a note")
    parser.add_argument("text")
    parser.set_defaults(handler=run)


def run(args):
    saved = notes.append(paths.notes_file(args, "store"), args.text)
    print("added note {}".format(len(saved)))
    return 0
