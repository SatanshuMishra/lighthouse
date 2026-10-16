---
name: firing-schedule
description: Use when a potter asks how to fire a glaze, which cone it matures at, or what ramp, hold and cooling segments to program into their kiln controller.
---

# Firing schedule

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/schedule.py" "<glaze name>"` with the glaze the potter named.
2. Give the cone and then each segment as a numbered list the potter can key into a kiln controller.
3. When the script says the glaze is not in the studio table, say this is the studio's cone 6 default schedule and that the potter should test fire a tile before a full load.

Keep the reply short and practical.
