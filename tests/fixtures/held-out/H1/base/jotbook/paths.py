import os


def default_file():
    return os.environ.get("JOTBOOK_FILE") or os.path.join(os.path.expanduser("~"), ".jotbook.json")


def notes_file(args, option):
    chosen = vars(args).get(option)
    return chosen if chosen else default_file()
