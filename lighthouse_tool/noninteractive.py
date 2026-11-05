import os
import shlex
from typing import Dict, Mapping, Tuple

FIXED_VALUES: Tuple[Tuple[str, str], ...] = (
    ("GIT_TERMINAL_PROMPT", "0"),
    ("GCM_INTERACTIVE", "never"),
    ("GH_PROMPT_DISABLED", "1"),
    ("GIT_PAGER", "cat"),
    ("PAGER", "cat"),
)
SSH_VARIABLE = "GIT_SSH_COMMAND"
DEFAULT_SSH = shlex.quote(os.path.join(os.path.dirname(os.path.realpath(__file__)), "owner-ssh"))
SSH_OPTIONS = "-o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4"
GIT_CONFIG_COUNT = "GIT_CONFIG_COUNT"
GIT_CONFIG_KEY = "GIT_CONFIG_KEY_{}"
GIT_CONFIG_VALUE = "GIT_CONFIG_VALUE_{}"
GIT_CONFIG_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("http.lowSpeedLimit", "1"),
    ("http.lowSpeedTime", "60"),
)


class UnusableEnvironment(ValueError):
    pass


def existing_config_count(base: Mapping[str, str]) -> int:
    given = base.get(GIT_CONFIG_COUNT, "").strip()
    if given == "":
        return 0
    if not given.isdigit():
        raise UnusableEnvironment("{} is {!r}, not a whole number of git configuration pairs".format(GIT_CONFIG_COUNT, given))
    return int(given)


def ssh_command(base: Mapping[str, str]) -> str:
    given = base.get(SSH_VARIABLE, "").strip()
    if given.endswith(SSH_OPTIONS):
        return given
    return "{} {}".format(given or DEFAULT_SSH, SSH_OPTIONS)


def config_already_added(base: Mapping[str, str], count: int) -> bool:
    first = count - len(GIT_CONFIG_PAIRS)
    if first < 0:
        return False
    return all(
        base.get(GIT_CONFIG_KEY.format(first + offset)) == key and base.get(GIT_CONFIG_VALUE.format(first + offset)) == value
        for offset, (key, value) in enumerate(GIT_CONFIG_PAIRS)
    )


def config_entries(base: Mapping[str, str], count: int) -> Dict[str, str]:
    if config_already_added(base, count):
        return {}
    entries = {
        name: text
        for offset, (key, value) in enumerate(GIT_CONFIG_PAIRS)
        for name, text in ((GIT_CONFIG_KEY.format(count + offset), key), (GIT_CONFIG_VALUE.format(count + offset), value))
    }
    return {**entries, GIT_CONFIG_COUNT: str(count + len(GIT_CONFIG_PAIRS))}


def environment(base: Mapping[str, str]) -> Dict[str, str]:
    count = existing_config_count(base)
    return {
        **dict(base),
        **dict(FIXED_VALUES),
        SSH_VARIABLE: ssh_command(base),
        **config_entries(base, count),
    }
