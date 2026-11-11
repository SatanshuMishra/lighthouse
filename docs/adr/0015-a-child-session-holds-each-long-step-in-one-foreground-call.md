# A child session holds each long step in one foreground call

Status: accepted; supersedes the hold by completion notice in ADR-0012 for the child session

`lighthouse launch` starts the child session with the Bash tool's default and longest timeouts set to one week, and the child runs every long step, the suite, the acceptance checks and a profile measure, as one foreground Bash call with no timeout argument, so the call returns only when the step ends. ADR-0012 held a long step by its completion notice, which was shown on a session without a reply schema. ADR-0014 then gave the child a reply schema, and a session with one is asked for its structured reply the moment a turn ends. The only reply the schema admits is a verdict, so the first 0.8.0 child that ended a turn to wait for a profile measure released its worktrees and returned a blocked verdict 12 seconds after starting the step. On Claude Code 2.1.318 the Bash tool also moves a foreground call to the background after ten minutes and stops a background command ten minutes after that, so a step over twenty minutes could not be held either way under the tool's own ceilings. No wall-clock limit comes back: one week is the Bash tool's ceiling raised out of the way, not a limit lighthouse reads or judges by. The session a person starts still holds `lighthouse launch` by its completion notice, because it has no reply schema and lighthouse does not start it.

## Considered options

- Keeping the completion notice and adding a reply form that means still waiting: a session with a schema was shown to wait and reply again after the notice, but it needs a schema change the program owns, costs a forced reply at every hold, and leaves a destructive reply one misreading away.
- Foreground holds in fixed windows that the session calls again and again, as before ADR-0012: needs no raised ceiling, but turns every hold into polling, 7 turns against 4 for a 150 second step in the probe.
- Dropping the reply schema: brings back reading the verdict from prose, which ADR-0014 removed for losing findings.
