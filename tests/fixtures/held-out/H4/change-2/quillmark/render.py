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


def render(template, values):
    segments = parse(template)
    for segment in segments:
        if segment["kind"] == "field":
            segment["value"] = field_text(segment["value"], values)
            segment["kind"] = "text"
    return "".join(segment["value"] for segment in segments)
