#!/bin/sh
python3 - <<'PY'
import sys

from quillmark.render import render

template = "Dear {name|friend}, your table for {guests} is booked for {day}."
rows = [
    {"name": "Ada", "guests": 2, "day": "Friday"},
    {"guests": 4, "day": "Saturday"},
    {"name": "Bo", "guests": 3, "day": "Sunday"},
]
expected = [
    "Dear Ada, your table for 2 is booked for Friday.",
    "Dear friend, your table for 4 is booked for Saturday.",
    "Dear Bo, your table for 3 is booked for Sunday.",
]
letters = [render(template, row) for row in rows]
if letters != expected:
    print("mail merge rendered {} where {} was expected".format(letters, expected))
    sys.exit(1)
print("mail merge rendered every letter for its own row")
PY
