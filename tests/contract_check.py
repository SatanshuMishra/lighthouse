import json
import os
import re
from typing import Any, Dict, List

CONTRACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contracts")
K1_SCHEMA = os.path.join(CONTRACTS, "k1-acceptance.schema.json")
K3_SCHEMA = os.path.join(CONTRACTS, "k3-check-result.schema.json")

SUPPORTED_KEYWORDS = frozenset(
    [
        "$schema",
        "$id",
        "title",
        "description",
        "type",
        "enum",
        "const",
        "pattern",
        "minLength",
        "minItems",
        "minimum",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "if",
        "then",
        "else",
        "not",
        "anyOf",
        "$ref",
    ]
)


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _is_type(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise ValueError("unsupported type " + repr(name))


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


def _unescape_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_ref(ref: str, schema_folder: str) -> Dict[str, Any]:
    file_part, _, pointer = ref.partition("#")
    if not file_part:
        raise ValueError("unsupported $ref without a file: " + ref)
    target_path = os.path.join(schema_folder, file_part)
    node = _load(target_path)
    for token in [t for t in pointer.split("/") if t != ""]:
        node = node[_unescape_pointer_token(token)]
    return {"schema": node, "folder": os.path.dirname(target_path)}


def _validate(instance: Any, schema: Any, folder: str, where: str) -> List[str]:
    if schema is True:
        return []
    if schema is False:
        return [where + ": no value is allowed here"]
    unknown = sorted(set(schema) - SUPPORTED_KEYWORDS)
    if unknown:
        raise ValueError("unsupported schema keywords at " + where + ": " + ", ".join(unknown))

    found: List[str] = []

    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], folder)
        found.extend(_validate(instance, resolved["schema"], resolved["folder"], where))

    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, name) for name in names):
            found.append(where + ": expected type " + "/".join(names) + ", got " + json.dumps(instance))
            return found

    if "enum" in schema and not any(_same(instance, option) for option in schema["enum"]):
        found.append(where + ": " + json.dumps(instance) + " is not one of " + json.dumps(schema["enum"]))

    if "const" in schema and not _same(instance, schema["const"]):
        found.append(where + ": " + json.dumps(instance) + " is not " + json.dumps(schema["const"]))

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            found.append(where + ": shorter than " + str(schema["minLength"]) + " characters")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            found.append(where + ": " + json.dumps(instance) + " does not match " + schema["pattern"])

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            found.append(where + ": " + str(instance) + " is below " + str(schema["minimum"]))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            found.append(where + ": fewer than " + str(schema["minItems"]) + " items")
        if "items" in schema:
            for index, item in enumerate(instance):
                found.extend(_validate(item, schema["items"], folder, where + "[" + str(index) + "]"))

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                found.append(where + ": missing required key " + json.dumps(key))
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in instance:
                found.extend(_validate(instance[key], subschema, folder, where + "." + key))
        if schema.get("additionalProperties") is False:
            for key in sorted(set(instance) - set(properties)):
                found.append(where + ": unexpected key " + json.dumps(key))

    if "not" in schema and not _validate(instance, schema["not"], folder, where):
        found.append(where + ": matches a schema it must not match")

    if "anyOf" in schema:
        if all(_validate(instance, option, folder, where) for option in schema["anyOf"]):
            found.append(where + ": matches none of the anyOf schemas")

    if "if" in schema:
        if not _validate(instance, schema["if"], folder, where):
            if "then" in schema:
                found.extend(_validate(instance, schema["then"], folder, where))
        elif "else" in schema:
            found.extend(_validate(instance, schema["else"], folder, where))

    return found


def errors(instance: Any, schema_path: str) -> List[str]:
    absolute = os.path.abspath(schema_path)
    return _validate(instance, _load(absolute), os.path.dirname(absolute), "$")


def assert_valid(test: Any, instance: Any, schema_path: str) -> None:
    test.assertEqual([], errors(instance, schema_path))
