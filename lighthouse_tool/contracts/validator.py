import json
import os
import re
from collections import namedtuple

ANNOTATIONS = frozenset(("$schema", "$id", "title", "description", "$comment", "examples"))
SCHEMA_KEYWORDS = ("items", "if", "then", "else", "not", "contains", "propertyNames")
SCHEMA_LIST_KEYWORDS = ("anyOf", "allOf", "oneOf")
SCHEMA_MAP_KEYWORDS = ("properties", "$defs", "patternProperties")
VALUE_KEYWORDS = (
    "$ref",
    "type",
    "enum",
    "const",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "required",
    "additionalProperties",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minContains",
    "maxContains",
    "minProperties",
)
KEYWORDS = ANNOTATIONS | frozenset(SCHEMA_KEYWORDS + SCHEMA_LIST_KEYWORDS + SCHEMA_MAP_KEYWORDS + VALUE_KEYWORDS)
PATTERN_TOKEN = re.compile(r"\\.|\[(?:\\.|[^\]\\])*\]|.", re.DOTALL)
SCHEMA_SUFFIX = ".schema.json"

Scope = namedtuple("Scope", ("directory", "document"))


def schema_path(directory, name):
    return os.path.join(directory, name if name.endswith(SCHEMA_SUFFIX) else name + SCHEMA_SUFFIX)


def read_schema(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def unescape(token):
    return token.replace("~1", "/").replace("~0", "~")


def escape(token):
    return token.replace("~", "~0").replace("/", "~1")


def at_pointer(document, pointer):
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer %r does not start with /" % pointer)
    found = document
    for token in (unescape(part) for part in pointer.split("/")[1:]):
        found = found[int(token)] if isinstance(found, list) else found[token]
    return found


def resolve(scope, reference):
    target, _, pointer = reference.partition("#")
    if target == "":
        return scope, at_pointer(scope.document, pointer)
    if "/" in target or target.startswith("."):
        raise ValueError("$ref %r names a file outside the contracts folder" % reference)
    document = read_schema(os.path.join(scope.directory, target))
    return Scope(scope.directory, document), at_pointer(document, pointer)


def nested(schema):
    singles = tuple(schema[key] for key in SCHEMA_KEYWORDS if key in schema)
    listed = tuple(member for key in SCHEMA_LIST_KEYWORDS for member in schema.get(key, ()))
    mapped = tuple(member for key in SCHEMA_MAP_KEYWORDS for member in schema.get(key, {}).values())
    extra = (schema["additionalProperties"],) if isinstance(schema.get("additionalProperties"), dict) else ()
    return singles + listed + mapped + extra


def supported(schema):
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise ValueError("schema %r is not an object" % (schema,))
    unknown = sorted(key for key in schema if key not in KEYWORDS)
    if unknown:
        raise ValueError("unsupported JSON Schema keyword %r" % unknown[0])
    strange = tuple(name for name in type_names(schema) if name not in TYPE_CHECKS)
    if strange:
        raise ValueError("unsupported JSON Schema type %r" % (strange[0],))
    for member in nested(schema):
        supported(member)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def same(first, second):
    if isinstance(first, bool) or isinstance(second, bool):
        return isinstance(first, bool) and isinstance(second, bool) and first == second
    if is_number(first) and is_number(second):
        return first == second
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(same(one, other) for one, other in zip(first, second))
    if isinstance(first, dict) and isinstance(second, dict):
        return first.keys() == second.keys() and all(same(first[key], second[key]) for key in first)
    return type(first) is type(second) and first == second


TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "number": is_number,
    "integer": lambda value: is_number(value) and float(value).is_integer(),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


def type_names(schema):
    if "type" not in schema:
        return ()
    return tuple(schema["type"]) if isinstance(schema["type"], list) else (schema["type"],)


def shortened(text, most):
    return text if len(text) <= most else text[: most - 3] + "..."


def shown(value):
    return shortened(json.dumps(value, ensure_ascii=True, sort_keys=True), 120)


def one_line(pointer):
    return shortened(json.dumps(pointer, ensure_ascii=True)[1:-1], 200)


def failure(pointer, keyword, message):
    return ("#%s %s: %s" % (one_line(pointer), keyword, message),)


def child(pointer, token):
    return "%s/%s" % (pointer, escape(str(token)))


def type_errors(schema, value, pointer):
    names = type_names(schema)
    if not names or any(TYPE_CHECKS[name](value) for name in names):
        return ()
    return failure(pointer, "type", "%s is not of type %s" % (shown(value), " or ".join(names)))


def enum_errors(schema, value, pointer):
    if "enum" in schema and not any(same(value, option) for option in schema["enum"]):
        options = ", ".join(shown(option) for option in schema["enum"])
        return failure(pointer, "enum", "%s is not one of %s" % (shown(value), options))
    return ()


def const_errors(schema, value, pointer):
    if "const" in schema and not same(value, schema["const"]):
        return failure(pointer, "const", "%s is not %s" % (shown(value), shown(schema["const"])))
    return ()


def ecma_pattern(pattern):
    return "".join("\\Z" if token == "$" else token for token in PATTERN_TOKEN.findall(pattern))


def matches(pattern, value):
    return re.search(ecma_pattern(pattern), value) is not None


def string_errors(schema, value, pointer):
    if not isinstance(value, str):
        return ()
    short = (
        failure(pointer, "minLength", "%s is shorter than %d characters" % (shown(value), schema["minLength"]))
        if "minLength" in schema and len(value) < schema["minLength"]
        else ()
    )
    long = (
        failure(pointer, "maxLength", "holds %d characters, more than %d" % (len(value), schema["maxLength"]))
        if "maxLength" in schema and len(value) > schema["maxLength"]
        else ()
    )
    unmatched = (
        failure(pointer, "pattern", "%s does not match %s" % (shown(value), shown(schema["pattern"])))
        if "pattern" in schema and not matches(schema["pattern"], value)
        else ()
    )
    return short + long + unmatched


def number_errors(schema, value, pointer):
    if not is_number(value):
        return ()
    low = (
        failure(pointer, "minimum", "%s is less than %s" % (shown(value), shown(schema["minimum"])))
        if "minimum" in schema and value < schema["minimum"]
        else ()
    )
    high = (
        failure(pointer, "maximum", "%s is more than %s" % (shown(value), shown(schema["maximum"])))
        if "maximum" in schema and value > schema["maximum"]
        else ()
    )
    return low + high


def additional_schema(schema, key):
    if key in schema.get("properties", {}):
        return None
    if any(matches(pattern, key) for pattern in schema.get("patternProperties", {})):
        return None
    return schema.get("additionalProperties", True)


def object_errors(schema, value, pointer, scope):
    if not isinstance(value, dict):
        return ()
    properties = schema.get("properties", {})
    absent = tuple(
        finding
        for key in schema.get("required", ())
        if key not in value
        for finding in failure(pointer, "required", "lacks required property %s" % shown(key))
    )
    few = (
        failure(pointer, "minProperties", "%d properties; at least %d needed" % (len(value), schema["minProperties"]))
        if "minProperties" in schema and len(value) < schema["minProperties"]
        else ()
    )
    members = tuple(
        finding
        for key, member in properties.items()
        if key in value
        for finding in check(member, value[key], child(pointer, key), scope)
    )
    patterned = tuple(
        finding
        for pattern, member in schema.get("patternProperties", {}).items()
        for key in sorted(value)
        if matches(pattern, key)
        for finding in check(member, value[key], child(pointer, key), scope)
    )
    names = tuple(
        finding
        for key in sorted(value)
        if "propertyNames" in schema
        for finding in check(schema["propertyNames"], key, child(pointer, key), scope)
    )
    extra = tuple(
        finding
        for key in sorted(value)
        for finding in extra_errors(additional_schema(schema, key), value[key], child(pointer, key), key, scope)
    )
    return absent + few + members + patterned + names + extra


def extra_errors(rule, value, pointer, key, scope):
    if rule is None or rule is True:
        return ()
    if rule is False:
        return failure(pointer, "additionalProperties", "property %s is not allowed" % shown(key))
    return check(rule, value, pointer, scope)


def unique_errors(schema, value, pointer):
    if not schema.get("uniqueItems"):
        return ()
    repeats = tuple(index for index, item in enumerate(value) if any(same(item, earlier) for earlier in value[:index]))
    return failure(child(pointer, repeats[0]), "uniqueItems", "item repeats an earlier item") if repeats else ()


def contains_errors(schema, value, pointer, scope):
    if "contains" not in schema:
        return ()
    count = sum(1 for index, item in enumerate(value) if not check(schema["contains"], item, child(pointer, index), scope))
    least = schema.get("minContains", 1)
    most = schema.get("maxContains")
    few = (
        failure(pointer, "minContains", "%d items match contains; at least %d needed" % (count, least))
        if count < least
        else ()
    )
    many = (
        failure(pointer, "maxContains", "%d items match contains; at most %d allowed" % (count, most))
        if most is not None and count > most
        else ()
    )
    return few + many


def array_errors(schema, value, pointer, scope):
    if not isinstance(value, list):
        return ()
    short = (
        failure(pointer, "minItems", "%d items; at least %d needed" % (len(value), schema["minItems"]))
        if "minItems" in schema and len(value) < schema["minItems"]
        else ()
    )
    long = (
        failure(pointer, "maxItems", "%d items; at most %d allowed" % (len(value), schema["maxItems"]))
        if "maxItems" in schema and len(value) > schema["maxItems"]
        else ()
    )
    members = (
        tuple(
            finding
            for index, item in enumerate(value)
            for finding in check(schema["items"], item, child(pointer, index), scope)
        )
        if "items" in schema
        else ()
    )
    return short + long + members + unique_errors(schema, value, pointer) + contains_errors(schema, value, pointer, scope)


def conditional_errors(schema, value, pointer, scope):
    if "if" not in schema:
        return ()
    branch = "else" if check(schema["if"], value, pointer, scope) else "then"
    return check(schema[branch], value, pointer, scope) if branch in schema else ()


def logic_errors(schema, value, pointer, scope):
    negated = (
        failure(pointer, "not", "value matches a schema it must not match")
        if "not" in schema and not check(schema["not"], value, pointer, scope)
        else ()
    )
    alternatives = (
        failure(pointer, "anyOf", "value matches none of the alternatives: " + "; ".join(
            "; ".join(check(member, value, pointer, scope)) for member in schema["anyOf"]
        ))
        if "anyOf" in schema and all(check(member, value, pointer, scope) for member in schema["anyOf"])
        else ()
    )
    combined = tuple(finding for member in schema.get("allOf", ()) for finding in check(member, value, pointer, scope))
    return conditional_errors(schema, value, pointer, scope) + negated + alternatives + combined + exclusive_errors(schema, value, pointer, scope)


def exclusive_errors(schema, value, pointer, scope):
    if "oneOf" not in schema:
        return ()
    outcomes = tuple(check(member, value, pointer, scope) for member in schema["oneOf"])
    passing = sum(1 for outcome in outcomes if not outcome)
    if passing == 1:
        return ()
    if passing == 0:
        return failure(pointer, "oneOf", "value matches none of the alternatives: " + "; ".join("; ".join(outcome) for outcome in outcomes))
    return failure(pointer, "oneOf", "value matches %d alternatives; exactly one allowed" % passing)


def reference_errors(schema, value, pointer, scope):
    if "$ref" not in schema:
        return ()
    target_scope, target = resolve(scope, schema["$ref"])
    supported(target)
    return check(target, value, pointer, target_scope)


def check(schema, value, pointer, scope):
    if schema is True:
        return ()
    if schema is False:
        return failure(pointer, "false", "no value is allowed here")
    return (
        reference_errors(schema, value, pointer, scope)
        + type_errors(schema, value, pointer)
        + enum_errors(schema, value, pointer)
        + const_errors(schema, value, pointer)
        + string_errors(schema, value, pointer)
        + number_errors(schema, value, pointer)
        + object_errors(schema, value, pointer, scope)
        + array_errors(schema, value, pointer, scope)
        + logic_errors(schema, value, pointer, scope)
    )


def errors(schema, value, directory):
    supported(schema)
    return check(schema, value, "", Scope(directory, schema))


def errors_against(directory, name, value):
    return errors(read_schema(schema_path(directory, name)), value, directory)
