# Work runs to its end, and every wait ends on its condition or its process's exit

Status: accepted; supersedes ADR-0011, and the hold by repeated lighthouse wait calls in ADR-0006

lighthouse puts no wall-clock limit on any step, check, child session or wait: a slow suite, check or session runs to its end and is judged by its exit status, so a long but healthy run is never reported blocked or could-not-run because a timer derived from measured durations ran out. Instead nothing lighthouse starts can wait forever: every process gets closed input and a non-interactive environment with git's and ssh's own dead-peer detection, every wait names the exit file of the process it waits on and ends when its check passes or that file appears, and the skills hold a long step by its completion notice, since a headless claude -p session on Claude Code 2.1.317 was shown to wait for its background commands and be told when they end. A start command stays in the foreground until it is stopped, and lighthouse release stops every start command a run started, so no server keeps a session waiting. The profile's suite.timeout_minutes is retired. A project command that hangs without exiting is the project's to bound; lighthouse adds no timer for it, and for test runners readiness asks the owner about each one that does not bound its tests (ADR-0013).

## Considered options

- Limits derived from measured durations (ADR-0011): ended healthy long runs as blocked and needed a deadline file every hold had to read.
- A fixed window on each wait that the session calls again and again: a timer by another name, and turns every hold into polling.
- Waiting on a process id: a command started with run_in_background does not give the session its process id; an exit file does the same job and survives the call that started it.
