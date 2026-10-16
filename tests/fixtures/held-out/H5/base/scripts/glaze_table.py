import json
import os

TABLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "glazes.json")


def load():
    with open(TABLE, encoding="utf-8") as handle:
        return json.load(handle)


def find(name):
    wanted = name.strip().lower()
    return next((glaze for glaze in load()["glazes"] if glaze["name"].lower() == wanted), None)
