import json
import os
import re
from typing import Any, Callable, Dict, List

CONTRACTS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "contracts")


def problems(instance: Any, schema_name: str) -> List[str]:
    path = os.path.join(CONTRACTS, schema_name)
    return violations(instance, loaded(path), os.path.dirname(path), "$")


def loaded(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def is_type(value: Any, name: str) -> bool:
    checks: Dict[str, Callable[[Any], bool]] = {
        "object": lambda found: isinstance(found, dict),
        "array": lambda found: isinstance(found, list),
        "string": lambda found: isinstance(found, str),
        "boolean": lambda found: isinstance(found, bool),
        "null": lambda found: found is None,
        "integer": lambda found: is_number(found) and float(found).is_integer(),
        "number": is_number,
    }
    if name not in checks:
        raise ValueError("unsupported type {}".format(name))
    return checks[name](value)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if is_number(left) and is_number(right):
        return left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def referenced(reference: str, folder: str) -> Dict[str, Any]:
    file_name, _, pointer = reference.partition("#")
    if not file_name:
        raise ValueError("unsupported $ref {}".format(reference))
    path = os.path.join(folder, file_name)
    node = loaded(path)
    for token in [token for token in pointer.split("/") if token]:
        node = node[token.replace("~1", "/").replace("~0", "~")]
    return {"schema": node, "folder": os.path.dirname(path)}


def violations(instance: Any, schema: Any, folder: str, where: str) -> List[str]:
    if schema is True:
        return []
    if schema is False:
        return ["{}: no value is allowed".format(where)]
    if "$ref" in schema:
        target = referenced(schema["$ref"], folder)
        found = violations(instance, target["schema"], target["folder"], where)
    else:
        found = []
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(is_type(instance, name) for name in names):
            return found + ["{}: expected {}, got {}".format(where, " or ".join(names), json.dumps(instance))]
    return (
        found
        + value_violations(instance, schema, where)
        + array_violations(instance, schema, folder, where)
        + object_violations(instance, schema, folder, where)
        + combined_violations(instance, schema, folder, where)
    )


def value_violations(instance: Any, schema: Dict[str, Any], where: str) -> List[str]:
    found = []
    if "enum" in schema and not any(equal(instance, option) for option in schema["enum"]):
        found.append("{}: {} is not one of {}".format(where, json.dumps(instance), json.dumps(schema["enum"])))
    if "const" in schema and not equal(instance, schema["const"]):
        found.append("{}: {} is not {}".format(where, json.dumps(instance), json.dumps(schema["const"])))
    if isinstance(instance, str) and "minLength" in schema and len(instance) < schema["minLength"]:
        found.append("{}: shorter than {} characters".format(where, schema["minLength"]))
    if isinstance(instance, str) and "pattern" in schema and re.search(schema["pattern"], instance) is None:
        found.append("{}: {} does not match {}".format(where, json.dumps(instance), schema["pattern"]))
    if is_number(instance) and "minimum" in schema and instance < schema["minimum"]:
        found.append("{}: {} is below {}".format(where, instance, schema["minimum"]))
    return found


def array_violations(instance: Any, schema: Dict[str, Any], folder: str, where: str) -> List[str]:
    if not isinstance(instance, list):
        return []
    found = []
    if "minItems" in schema and len(instance) < schema["minItems"]:
        found.append("{}: fewer than {} items".format(where, schema["minItems"]))
    if "items" in schema:
        for index, item in enumerate(instance):
            found.extend(violations(item, schema["items"], folder, "{}[{}]".format(where, index)))
    return found


def object_violations(instance: Any, schema: Dict[str, Any], folder: str, where: str) -> List[str]:
    if not isinstance(instance, dict):
        return []
    found = ["{}: missing {}".format(where, json.dumps(key)) for key in schema.get("required", []) if key not in instance]
    properties = schema.get("properties", {})
    for key, child in properties.items():
        if key in instance:
            found.extend(violations(instance[key], child, folder, "{}.{}".format(where, key)))
    if schema.get("additionalProperties") is False:
        found.extend("{}: unexpected {}".format(where, json.dumps(key)) for key in sorted(set(instance) - set(properties)))
    return found


def combined_violations(instance: Any, schema: Dict[str, Any], folder: str, where: str) -> List[str]:
    found = []
    if "not" in schema and not violations(instance, schema["not"], folder, where):
        found.append("{}: matches a schema it must not match".format(where))
    if "anyOf" in schema and all(violations(instance, option, folder, where) for option in schema["anyOf"]):
        found.append("{}: matches none of its allowed shapes".format(where))
    if "if" in schema:
        branch = "else" if violations(instance, schema["if"], folder, where) else "then"
        if branch in schema:
            found.extend(violations(instance, schema[branch], folder, where))
    return found
