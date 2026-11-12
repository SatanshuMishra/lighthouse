# Changelog

## 0.8.6

- A neighbour's trials run on core only when it fails on FEATURE, and every trial session starts at the five-minute cache rate with a stated model and effort. The test skill had each model-driven case run its trials on both builds, while the verdict reads a neighbour's core trials only when no more than one of its FEATURE trials passed. On 13 recorded runs every one of the 68 paths passed on FEATURE, so the 38 core trial sessions changed no outcome and cost 15.39 of the 58.58 dollars those runs spent in lighthouse. The 88 recorded trial sessions never waited more than 20 seconds between two turns, and repricing them at the five-minute rate cuts their 35.41 dollars to between 24.99 and 29.35. The skill and the driver now say so: core trials only for a neighbour failing on FEATURE, `CLAUDE_CODE_PROMPT_CACHE_TTL=5m` on each trial session's command, and `--model opus --effort high` unless the recorded driver names its own.

## 0.8.5

- `lighthouse spend` takes each step and path from the line `lighthouse mark` wrote, and no longer from the text of the command that ran it. It read the mark calls back out of each session's Bash commands without expanding shell variables, so a mark written as `--path "$P"` was reported as a path named `$P`, a mark written in a loop was dropped, and neither was matched to its line in `marks.jsonl`, which left the folder of the path's trial sessions unattributed. On the 13 recorded runs, 34 of the 39 path rows carried a variable's name, 4 of the 68 recorded paths had a row, and 45.26 of the 65.28 dollars those sessions cost sat outside any step. Each line of `marks.jsonl` now belongs to the session whose Bash call was running when the line was written. Where two sessions had a call running, the one whose result prints the line is taken, then the one whose command names the line's step, build and path, then the one that wrote another mark of the same step, build and path. A line no rule settles still opens its step or path and owns its folder, and only its writer's own messages stay shared. Replayed on the same 13 runs, all 640 mark lines have one writer, all 68 recorded paths have a row, no row carries a variable's name, and 20.59 dollars sit outside any step; with any one of the three rules removed, 2, 6 or 12 lines have no one writer. Without a marks file the commands are read as before.
- Steps and paths whose marks one Bash call wrote are listed in the order the marks were written, where their order was left to chance.

## 0.8.4

- The child session and the driver agent state the effort they run at. `lighthouse launch` named the child's model and no effort, so the child ran at whatever the machine's Claude settings or a `CLAUDE_CODE_EFFORT_LEVEL` in the caller's environment named; on the 13 recorded runs that was high, by the settings alone. The child is now started with `--effort high`, and `CLAUDE_CODE_EFFORT_LEVEL` is dropped from its environment, because a live session showed that variable overriding both the flag and an agent file's own effort. The driver agent states `effort: medium`, the level its 122 recorded replies ran at as what a Sonnet agent with no level falls to; with the flag now on the child, a driver with no level of its own would have taken the child's.

## 0.8.3

- `lighthouse suite` runs FEATURE's suite first and, when the profile's suite names no JUnit report and runs its two builds one after the other, builds core and runs its suite only when FEATURE's suite fails. Core's result has two readers: the comparison that tells a failure that was already there from a new one, which needs it only when FEATURE fails, and a neighbour path proven by the suite, which needs each test to have passed on core too and exists only with a JUnit report. With no report and a passing FEATURE suite nothing read it, and `core` is now null in that result. Of the 12 suite steps on record, none names a JUnit report and FEATURE's suite passed in 10; core's suite ran fresh in 9 of those, and in the 4 whose builds ran one after the other it took 25.1 minutes, about 9 in each of two unattended runs on a project whose suite takes that long. In the one step where both suites failed, core's result is what marked the failure as already there. With a JUnit report nothing changes, and nothing changes for a profile whose suite is `isolated`: its two builds already run together, so skipping core would save no time and a failing FEATURE suite would wait for core afterwards.

## 0.8.2

- `lighthouse profile measure` no longer runs the project's suite. Its `suite_seconds` and `suite_exit` were written into the profile for the time limits 0.8.0 removed, and no step, skill or query has read them since, while each run's record already holds how long its own suite took on each build. In an unattended run on a project whose suite takes about ten minutes, the measure lighthouse:doctor ran after a profile repair spent 576 of the profile step's 601 seconds on that one suite run, before the run's suite step ran the same suite on both builds. Measure still runs setup, build, the start command with its readiness check and each surface's `reach` command, and still sets each surface's `available`. A profile that already holds the two keys still passes the check.

## 0.8.1

- The child session holds every long step, the suite, the acceptance checks and a profile measure, as one foreground Bash call that asks for a timeout of one week, which `lighthouse launch` allows by raising the Bash tool's longest timeout. The tool's default stays two minutes, and launch drops a default it inherits, so a command that hangs is still moved to the background: in a probe, a server started in the foreground held a session with both timeouts raised until the probe ended it at 420 seconds, and a session with only the longest raised finished in 141. Under 0.8.0 the child started a long step in the background and ended its turn to wait; a session with a reply schema is asked for its reply the moment a turn ends, so the first 0.8.0 child released its worktrees and returned a blocked verdict 12 seconds after starting a profile measure. `docs/adr/0015` records the decision.
- lighthouse:init and lighthouse:doctor run `lighthouse profile measure` in the foreground inside a lighthouse:test child session, and by its completion notice in any other session.
- The driver agent runs `lighthouse wait` in the foreground and never ends its turn while a wait or a command it started is still running.
- Every process the child or a driver starts in the background, a build's start command included, asks for the one-week timeout too. The Bash tool stops a background command ten minutes after its start when it asks for no timeout, and a process stopped that way writes no exit file: in a probe, a 780 second step started without the timeout was stopped at about 600 seconds and the hold on it never saw an exit file, and started with the timeout it ran to its end.

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
