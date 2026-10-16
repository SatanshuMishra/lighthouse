---
name: firing-log
description: Use when a potter says they have loaded, started or finished a kiln firing of a glaze and wants it recorded in their firing log.
---

# Firing log

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/schedule.py" --json "<glaze name>" | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_firing.py"` with the glaze the potter named.
2. Open your reply with the line `Firing logged:` and then repeat the line log_firing.py printed, which gives the firing's number, the glaze and its cone.
3. When either script fails, say the firing was not logged and show the message it printed.

Keep the reply short.
