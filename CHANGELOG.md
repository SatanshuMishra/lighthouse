# Changelog

## 0.8.1

- The child session holds every long step, the suite, the acceptance checks and a profile measure, as one foreground Bash call that asks for a timeout of one week, which `lighthouse launch` allows by raising the Bash tool's longest timeout. The tool's default stays two minutes, and launch drops a default it inherits, so a command that hangs is still moved to the background: in a probe, a server started in the foreground held a session with both timeouts raised until the probe ended it at 420 seconds, and a session with only the longest raised finished in 141. Under 0.8.0 the child started a long step in the background and ended its turn to wait; a session with a reply schema is asked for its reply the moment a turn ends, so the first 0.8.0 child released its worktrees and returned a blocked verdict 12 seconds after starting a profile measure. `docs/adr/0015` records the decision.
- lighthouse:init and lighthouse:doctor run `lighthouse profile measure` in the foreground inside a lighthouse:test child session, and by its completion notice in any other session.
- The driver agent runs `lighthouse wait` in the foreground and never ends its turn while a wait or a command it started is still running.

## 0.8.0

Every hand-off lighthouse writes or reads now has one owned format, checked by its producer before it is written, and lighthouse puts no wall-clock limit on any step.

### Time limits removed

- Every wall-clock limit is removed: limits.json, the step limits, the child session limit, the wait windows and the profile's suite.timeout_minutes are gone.
- lighthouse profile check now reports suite.timeout_minutes as retired, and lighthouse:doctor removes it from the profile.
- Every wait ends on its own check passing or on the awaited process's exit file, never on a clock.

### Nothing waits on input

- Every process lighthouse starts runs with no input, its stdin closed.
- Every process runs in a non-interactive environment: git, the git credential manager and gh never prompt, pagers are off, ssh runs in batch mode with dead-peer detection, and git aborts a stalled transfer.

### Owned formats

- lighthouse vendors byte-identical copies of the program's validator and of the H11, H13, H14, H15 and H16 schemas, each an owned format that lighthouse produces or reads.
- The interphase record is checked against the H11 owned format before its acceptance lines are read.
- Producers check before writing: the verdict line (H13), the findings (H14) and the pull request fields (H15) are each validated against their owned format immediately before they are written, and a failure stops at that step naming the schema errors.
- lighthouse findings validates the drafted findings and writes the findings file only when they match the H14 owned format.
- The child session's reply arrives through structured output; a reply that fails its owned format is re-asked once of the same session with the errors, and a second failure blocks the run naming those errors.
- Consumers refuse a hand-off that does not match its owned format instead of dropping, defaulting, coercing or truncating it, including the rendered pull request read through the H16 owned format.

### Pull requests

- The pull request is composed through pull-request render --fields and opened with that title and body unchanged.
- The gh pr create fallback is removed; the pull request opens through the create_pull_request tool only.

## 0.7.0

lighthouse readiness lists a `test-bound:<runner>` item for each test runner the suite command reaches that does not bound each test in the project's own configuration, because nothing else ends a hung test.
