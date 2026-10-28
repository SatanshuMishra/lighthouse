import os
from typing import Optional

LIMITS = "limits.json"
CHECKS = "checks.jsonl"
PLAN = "plan.json"
RECORD = "record.json"
SPEC_SUFFIX = ".md"
RECORD_SUFFIX = ".record.json"


def record_beside(spec: Optional[str]) -> Optional[str]:
    if spec is None or not spec.endswith(SPEC_SUFFIX):
        return None
    path = spec[: -len(SPEC_SUFFIX)] + RECORD_SUFFIX
    return path if os.path.isfile(path) else None
