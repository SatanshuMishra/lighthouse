from quillmark.parser import parse


class MissingField(KeyError):
    pass


def segment_text(segment, values):
    if segment["kind"] == "text":
        return segment["value"]
    if segment["value"] not in values:
        raise MissingField(segment["value"])
    return str(values[segment["value"]])


def render(template, values):
    return "".join(segment_text(segment, values) for segment in parse(template))
