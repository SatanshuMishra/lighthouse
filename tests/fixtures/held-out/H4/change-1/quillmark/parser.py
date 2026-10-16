import functools
import re

FIELD = re.compile(r"\{([^{}]+)\}")


@functools.lru_cache(maxsize=256)
def parse(template):
    segments = []
    position = 0
    for match in FIELD.finditer(template):
        if match.start() > position:
            segments.append({"kind": "text", "value": template[position:match.start()]})
        segments.append({"kind": "field", "value": match.group(1).strip()})
        position = match.end()
    if position < len(template):
        segments.append({"kind": "text", "value": template[position:]})
    return segments


def fields(template):
    return [segment["value"] for segment in parse(template) if segment["kind"] == "field"]
