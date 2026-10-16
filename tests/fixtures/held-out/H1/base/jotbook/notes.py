import json
import os


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def append(path, text):
    saved = load(path) + [text]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(saved, handle)
    return saved
