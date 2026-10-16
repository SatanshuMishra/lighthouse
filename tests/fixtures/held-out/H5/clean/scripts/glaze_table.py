import json
import os
import sys

TABLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "glazes.json")


def load():
    with open(TABLE, encoding="utf-8") as handle:
        return json.load(handle)


def default_notice(name):
    return "{} is not in the studio table; using the cone 6 default schedule. Test fire a tile first.".format(name)


def find(name):
    table = load()
    wanted = name.strip()
    known = next((glaze for glaze in table["glazes"] if glaze["name"].lower() == wanted.lower()), None)
    if known is not None:
        return known
    print(default_notice(wanted), file=sys.stderr)
    return {**table["default"], "name": wanted}
