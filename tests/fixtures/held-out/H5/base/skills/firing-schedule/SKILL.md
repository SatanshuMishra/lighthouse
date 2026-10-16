---
name: firing-schedule
description: Use when a potter asks how to fire a glaze, which cone it matures at, or what ramp, hold and cooling segments to program into their kiln controller.
---

# Firing schedule

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/schedule.py" "<glaze name>"` with the glaze the potter named.
2. When the script prints a schedule, give the cone and then each segment as a numbered list the potter can key into a kiln controller.
3. When the script says it has no schedule for the glaze, say the studio table does not list it and ask which cone the glaze's maker recommends.

Keep the reply short and practical.
