import json
import os
from datetime import date

DEFAULT_FILE = "milepost.json"


def data_path():
    return os.environ.get("MILEPOST_DATA") or DEFAULT_FILE


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save(path, trips):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(trips, handle, indent=2)
        handle.write("\n")


def trip(day, place, km):
    return {"date": date.fromisoformat(day).isoformat(), "place": place, "km": round(float(km), 1)}


def numbered(trips):
    return list(enumerate(trips, start=1))


def describe(number, entry):
    return "{}. {}  {}  {:.1f} km".format(number, entry["date"], entry["place"], entry["km"])
