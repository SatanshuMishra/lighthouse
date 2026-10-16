from kilnroom import pieces

ROUTES = (
    ("GET", "/pieces", pieces.list_pieces),
    ("GET", "/pieces/{id}", pieces.show_piece),
    ("POST", "/pieces", pieces.add_piece),
    ("DELETE", "/pieces/{id}", pieces.withdraw_piece),
)


def parts_of(path):
    return tuple(part for part in path.split("/") if part)


def is_parameter(part):
    return part.startswith("{") and part.endswith("}")


def params_for(pattern, path):
    expected, given = parts_of(pattern), parts_of(path)
    if len(expected) != len(given):
        return None
    if not all(is_parameter(want) or want == got for want, got in zip(expected, given)):
        return None
    return {want[1:-1]: got for want, got in zip(expected, given) if is_parameter(want)}


def match(method, path):
    found = (
        (pattern, action, params_for(pattern, path))
        for route_method, pattern, action in ROUTES
        if route_method == method
    )
    return next(((pattern, action, params) for pattern, action, params in found if params is not None), None)
