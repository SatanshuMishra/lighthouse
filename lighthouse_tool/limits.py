from typing import Any, Dict, NamedTuple

from lighthouse_tool.records import is_number

FLOOR_SECONDS = 60
UNMEASURED_SUITE_SECONDS = 3600
MEASURED_MULTIPLE = 3
CHILD_SUITE_RUNS = 2
CHILD_STEP_RUNS = 6
CHILD_ALLOWANCE_SECONDS = 10800
RUN_ALLOWANCE_SECONDS = 600
CHILD_STEPS = ("setup_seconds", "build_seconds", "start_seconds")
PREPARATION_STEPS = ("setup_seconds", "build_seconds")


class Limits(NamedTuple):
    suite_seconds: float
    check_seconds: float
    child_seconds: float
    run_seconds: float
    build_seconds: float


def section(holder: Any, name: str) -> Dict[str, Any]:
    found = holder.get(name) if isinstance(holder, dict) else None
    return found if isinstance(found, dict) else {}


def seconds_of(holder: Dict[str, Any], name: str) -> float:
    value = holder.get(name)
    return value if is_number(value) else 0


def measured_of(profile: Any) -> Dict[str, Any]:
    return section(profile, "measured")


def suite_limit(profile: Any) -> float:
    minutes = section(profile, "suite").get("timeout_minutes")
    if is_number(minutes) and minutes > 0:
        return minutes * 60
    measured = measured_of(profile)
    if is_number(measured.get("suite_seconds")):
        return max(FLOOR_SECONDS, MEASURED_MULTIPLE * measured["suite_seconds"])
    return UNMEASURED_SUITE_SECONDS


def driver_seconds(measured: Dict[str, Any]) -> float:
    return sum(seconds_of(driver, "seconds") for driver in section(measured, "drivers").values() if isinstance(driver, dict))


def of(profile: Any) -> Limits:
    measured = measured_of(profile)
    suite_seconds = suite_limit(profile)
    child_seconds = (
        CHILD_SUITE_RUNS * suite_seconds
        + CHILD_STEP_RUNS * sum(seconds_of(measured, name) for name in CHILD_STEPS)
        + CHILD_STEP_RUNS * driver_seconds(measured)
        + CHILD_ALLOWANCE_SECONDS
    )
    build_seconds = max(suite_seconds, MEASURED_MULTIPLE * sum(seconds_of(measured, name) for name in PREPARATION_STEPS))
    return Limits(suite_seconds, suite_seconds, child_seconds, child_seconds + RUN_ALLOWANCE_SECONDS, build_seconds)
