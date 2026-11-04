import os
from typing import Any, List, Tuple

from lighthouse_tool.contracts import validator
from lighthouse_tool.repo import Refusal

CONTRACTS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "contracts")
ERROR_JOINER = "; "


class FormatRefusal(Refusal):
    def __init__(self, message: str, schema: str, errors: Tuple[str, ...]) -> None:
        super().__init__(message)
        self.schema = schema
        self.errors = errors


def schema_file(name: str) -> str:
    return os.path.basename(validator.schema_path(CONTRACTS, name))


def schema_errors(name: str, value: Any) -> List[str]:
    try:
        return list(validator.errors_against(CONTRACTS, name, value))
    except OSError as error:
        raise Refusal("cannot read the owned format {}: {}".format(schema_file(name), error.strerror or error))
    except (ValueError, KeyError, IndexError) as error:
        raise Refusal("the owned format {} cannot be applied: {}".format(schema_file(name), error))


def joined(errors: List[str]) -> str:
    return ERROR_JOINER.join(errors)


def check_before_writing(target: str, name: str, value: Any) -> Any:
    errors = schema_errors(name, value)
    if errors:
        raise FormatRefusal(
            "refusing to write {}: it fails {}: {}".format(target, schema_file(name), joined(errors)),
            schema_file(name),
            tuple(errors),
        )
    return value


def read_through(producer: str, source: str, name: str, value: Any) -> Any:
    errors = schema_errors(name, value)
    if errors:
        raise FormatRefusal(
            "{} from {} fails {}: {}".format(source, producer, schema_file(name), joined(errors)),
            schema_file(name),
            tuple(errors),
        )
    return value
