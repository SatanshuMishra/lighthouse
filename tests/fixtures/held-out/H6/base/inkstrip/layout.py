import textwrap

WIDTH = 24
MAX_LINES = 4


class LabelError(Exception):
    pass


def lay_out(rows):
    lines = tuple(line for row in rows for line in textwrap.wrap(row, WIDTH))
    if not lines:
        raise LabelError("a label needs at least one line of text")
    if len(lines) > MAX_LINES:
        raise LabelError("a label holds at most {} lines and this one needs {}".format(MAX_LINES, len(lines)))
    return lines


def framed(lines):
    border = "+" + "-" * WIDTH + "+"
    return (border,) + tuple("|" + line.ljust(WIDTH) + "|" for line in lines) + (border,)
