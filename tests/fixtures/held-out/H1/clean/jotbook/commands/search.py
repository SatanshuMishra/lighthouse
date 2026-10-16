from jotbook import notes, paths

NAME = "search"


def register(subparsers, shared):
    parser = subparsers.add_parser(NAME, parents=[shared], help="print the notes that contain a term")
    parser.add_argument("term")
    parser.set_defaults(handler=run)


def run(args):
    term = args.term.lower()
    numbered = enumerate(notes.load(paths.notes_file(args, "notebook")), start=1)
    matches = [(number, text) for number, text in numbered if term in text.lower()]
    for number, text in matches:
        print("{}. {}".format(number, text))
    return 0 if matches else 1
