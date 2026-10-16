from quillmark.parser import parse


class MissingField(KeyError):
    pass


def field_text(field, values):
    name, has_default, default = field.partition("|")
    if name in values:
        return str(values[name])
    if has_default:
        return default
    raise MissingField(name)


def segment_text(segment, values):
    return field_text(segment["value"], values) if segment["kind"] == "field" else segment["value"]


def render(template, values):
    return "".join(segment_text(segment, values) for segment in parse(template))
