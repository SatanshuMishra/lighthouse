# lighthouse:test runs its work in a child session

Status: accepted

Run inline, lighthouse:test re-read its caller's whole history (200 to 360 thousand tokens inside a pipeline session) on every turn, and its driver subagents lost their five-minute prompt cache during long holds and rewrote their context on waking. So the skill only launches: a child claude -p session started from the results folder, marked by a --child flag in its prompt, does the work with a fresh context on Opus, the caller holds with repeated lighthouse wait calls, and drivers run as lighthouse's own driver agent on Sonnet with a one-hour cache.

## Considered options

- A context: fork skill: fresh context, but it has no Agent tool, so it cannot dispatch drivers.
- A subagent: also has no Agent tool.
- An environment variable marking the child: every process the child starts, including plugin trial sessions, would inherit it.
- A completion notice instead of wait calls: a headless claude -p parent ends while its background command still runs.
