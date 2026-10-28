# lighthouse

lighthouse is a Claude Code plugin that proves a FEATURE branch of any kind of software works before it merges into its core branch: the project's own suite on both branches, the running product used the way a person or calling program uses it, and the surfaces next to the change. It reports a verdict with evidence, never fixes anything, and opens the FEATURE pull request when the verdict is green or unproven, as a draft for unproven, or when the run is marked final.

## Install

```sh
claude plugin marketplace add SatanshuMishra/lighthouse
claude plugin install lighthouse@lighthouse
```

It needs Python 3.9 or later and git on macOS or Linux, and uses gh when present. It works on its own, with no other plugin.

## Skills

| Skill | Flags | What it does |
|---|---|---|
| `lighthouse:init` | `--repo <path>`, `--unattended` | Reads the codebase and writes `.lighthouse/profile.json`, marking every fact it cannot confirm unconfirmed and every outward-facing action not confirmed safe off-limits. |
| `lighthouse:doctor` | `--repo <path>`, `--unattended` | Runs the profile and credentials checks and repairs the profile, changing only `.lighthouse/profile.json`; runs init when the profile is missing. |
| `lighthouse:test` | `--repo <path>`, `--core <branch>`, `--feature <branch>`, `--results <dir>`, `--previous <dir>` when an earlier run's results folder exists, `--spec <path>` when a spec exists, `--record <path>` when an interphase record holds the acceptance lines, `--final` | Starts `lighthouse launch` in the background, holds with `lighthouse wait` until the child session writes its verdict line, and ends with that line. The child session, started with `--child`, tests the FEATURE branch against the core branch in bypassPermissions mode. |

Only init and doctor, when a person invokes them directly, ask anything, and only questions about facts, never a credential value. lighthouse:test never asks and runs them with `--unattended`; when `lighthouse profile check` lists upgrades, it runs doctor once for them and carries on whatever doctor does.

lighthouse:test does its work in a child `claude -p` session, so the calling session's history is never re-read. The child never asks anything, never narrows scope to save time, holds for a condition only with `lighthouse wait`, never with a blind sleep, and records an environment problem it cannot fix, such as a throttled VM or a sleeping host, with its paths unproven and that reason.

## Agents

| Agent | What it does |
|---|---|
| `lighthouse:driver` | Drives one surface's product paths with the surface's recorded driver for the lighthouse:test child session, saves evidence where it is told, marks each path with `lighthouse mark`, holds only with `lighthouse wait`, measures contrast only with `lighthouse contrast`, and reports each path's outcome. It runs on Sonnet with a one-hour prompt cache (`experimental.cacheTtl: 1h`), so a long hold for a build or a VM does not rewrite its context. The child dispatches every driver through it and judges what it reports. |

## The profile

`.lighthouse/profile.json` in the repository under test describes how to build, start, reach, sign into and test the project. It is the only thing lighthouse writes into a project: lighthouse:test commits a new or changed profile to the FEATURE branch as its own commit, so it is reviewed in the FEATURE pull request.

| Field | Holds |
|---|---|
| `version` | 1 |
| `sources` | the repository-relative manifest, CI and test-configuration files it was built from |
| `suite` | `command`, run from the repository root; `junit`, a JUnit XML path or null; `timeout_minutes`, a number or null; `rerun`, a command run instead of the whole suite to rerun only the failed tests, or null; `isolated`, true when core's and FEATURE's suites can run at the same time |
| `surfaces` | each way the product is used: `name`, `kind`, `paths`, `driver`, `available`, `sign_in` (`method` none, command, token or form, and `command`), `credentials` (names only), `trials` (1, or 3 when model-backed or random) and `reach`, a command that exits 0 when this machine can drive the surface with its driver |
| `credentials` | `file`, the project's own gitignored credentials file or null; `names`, each mapped to `{"production": true or false}` |
| `facts` | each name mapped to `value`, `confirmed` and `recheck` |
| `off_limits` | plain-language actions lighthouse must never take |
| `setup`, `build`, `start`, `test_data` | optional: install, build and start commands, `start.ready`, and how test data is made |
| `measured` | optional, written by `lighthouse profile measure`: the seconds setup, build, the suite, the start command and each surface's `reach` command took, the suite's exit, the measured commit and `measured_at` |

`suite.rerun` takes the placeholders `{tests}` (the failing test ids as `classname.name`), `{names}` (their name attributes) and `{names_regex}` (`^(<names joined by |>)$`, each escaped), every substitution shell-quoted. It is used only when a JUnit report exists; the whole suite reruns when it is unset or null, no report exists, or the rerun cannot start, writes no readable report or lacks a test that failed the first time. `suite.isolated` defaults to false; set it true only when the suite uses no fixed ports, shared databases or shared folders, and `lighthouse suite` then prepares and runs both builds' suites concurrently. `lighthouse profile check` lists a valid profile lacking either key, or lacking `measured`, under `upgrades`, with exit 0.

`lighthouse profile measure --repo <path>` runs setup, build and the suite, starts the start command and runs its readiness check until it passes, and runs each surface's `reach` command, each once within its limit, then stops the started process. It writes their durations into `measured` and sets each surface's `available` from its `reach` command's exit, and writes no file but `.lighthouse/profile.json`. lighthouse:init runs it once the profile check passes, and lighthouse:doctor runs it when the check lists the `measured` upgrade or after any repair. Every time limit of a run comes from these durations: the suite and each acceptance line get the suite limit, `timeout_minutes` times 60 when stated, otherwise three times the measured suite seconds and never under 60, otherwise 3600; the child session and the whole run get limits built from the suite limit and the measured setup, build, start and driver seconds. A step that reaches its limit ends blocked or could-not-run with a reason naming the limit, never failed.

## Credentials

Credential values live in `~/.lighthouse/<repository folder>/credentials.env`, mode 0600, readable by its owner alone, or in the project's own gitignored file when the profile names one. The repository folder is the name of the folder holding the repository's main working tree. Put test accounts only there, typed by you: a name the profile marks production is refused. The profile records names, never values. Only `lighthouse with-credentials` reads the values and puts them into a child process, redacting them from its output, so no value ever appears in the chat, a report or any lighthouse output.

The profile a `with-credentials` call reads decides which names are production and which file holds the values. Without `--profile` it reads `.lighthouse/profile.json` at the root of the repository `--repo` is in, which is what lighthouse:doctor uses. lighthouse:test passes `--profile <results>/profile.json`, its checked copy of the FEATURE profile, because the user's checkout may hold an older profile or none.

## Readiness and answers

`lighthouse readiness` lists the open items before an unattended run: a missing profile, each unconfirmed fact without a stored answer, and each credential name absent or empty in the credentials file. `lighthouse answer` stores fact answers in `~/.lighthouse/<repository folder>/answers.json`, and `lighthouse profile publish` folds them into the profile on the FEATURE branch.

## Verdicts

`lighthouse verdict` computes the verdict from `findings.json`; the skill never writes one.

| Verdict | When |
|---|---|
| `blocked` | the suite is blocked, or FEATURE would not build or start |
| `failures` | a suite failure, an acceptance line that failed, a new-behaviour path that failed with no passing retry, a neighbour that failed again on retry while passing on core, or a flaky acceptance line or new-behaviour path |
| `unproven` | an acceptance line, a new-behaviour path or a neighbour lighthouse computed was not proven, the suite in `findings.json` disagrees with `suite.json`, or no check or new-behaviour path exists |
| `green` | otherwise |

The suite comes from `<results>/suite.json` alone; `findings.json` holds a copy of it, and a copy that disagrees leaves the run unproven. Acceptance lines are judged from `checks.jsonl` alone, by their check ids, never from a findings path. A passed or failed path, or a check result, counts only when each evidence file it names exists in the results folder and is not empty; otherwise it is unproven. A failed new-behaviour path with no retry recorded is a failure. A case that passes some but not every trial is flaky, and a flaky acceptance line or new-behaviour path is never green. A path on a surface whose `reach` command failed this run, or with no such result one the run's profile marks `available` false, is unproven. Anything not reached is unproven, never passed. An unproven verdict opens the FEATURE pull request in the same run, as a draft listing each unproven name under Risk, so no second run exists only to add `--final`.

Every product path driven in a run records its `check` in `findings.json` as `{"kind": ..., "why": ..., "tests": [...]}`: the lightest kind that still observes the expected outcome on the surface the intent names.

| Kind | When |
|---|---|
| `suite` | named tests in the project's suite assert the outcome and passed on FEATURE, and on core too for a neighbour; `tests` names them, and it needs a JUnit report |
| `direct` | an HTTP or command-line call whose response holds the outcome |
| `drive` | the surface's recorded driver, when the outcome is what a person sees or which component a model chose; a new-behaviour path whose intent names something seen on screen uses it |

`why` names the assertion or observation that shows the outcome. `lighthouse verdict` refuses a driven path with no check, another kind, an empty `why` or a suite check naming no test, judges a suite check unproven unless every named test passed as `<results>/suite.json` records it, accepts a carried path without a check, and shows each path's check in `report.md`.

## The verdict line

The last line lighthouse:test prints is one JSON object on one line, the contract with any caller:

```json
{"verdict": "green", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "dollars": 0.0, "pr": "https://github.com/owner/repo/pull/1"}
```

`pr` is the pull request's URL, or null when none was opened. `dollars` is the run's API-equivalent cost, or null when the findings carry none; a blocked line from `lighthouse verdict --blocked` has no `dollars`.

## The command

`bin/lighthouse <subcommand>` prints JSON on stdout and reasons on stderr, and exits 0 on success, 1 when the answer is no and 2 on a usage error or refusal.

| Subcommand | Flags |
|---|---|
| `version` | none |
| `change` | `--repo`, `--core`, `--feature` |
| `profile check` | `--repo`, `--profile` |
| `profile publish` | `--repo`, `--feature`, `--profile` |
| `readiness` | `--repo`, `--profile` |
| `answer` | `--repo`, `--set <fact>=<value>` (repeatable), `--profile` |
| `credentials init` | `--repo`, `--profile` |
| `credentials check` | `--repo`, `--profile` |
| `with-credentials` | `--repo`, `--profile`, `--cwd <dir>`, then `--sign-in <n>` to run the sign_in command of the surface at position n (from 0), with `--port <profile port>=<build port>` for each port the build runs on in its place, or `-- <command>` |
| `worktrees` | `--repo`, `--core`, `--feature`, `--results` |
| `suite` | `--repo`, `--core`, `--feature`, `--results`, `--profile` |
| `retest` | `--previous <dir>`, `--results <dir>`, `--repo`, `--core`, `--feature`, `--profile` |
| `release` | `--repo`, `--results` |
| `execute` | `--results <dir>`, `--record <path>`, `--spec <path>`, `--profile <file>` |
| `contrast` | `--foreground <colour>`, `--background <colour>`, `--source declared`, `tree` or `pixels`, `--large` |
| `profile measure` | `--repo`, `--profile` |
| `verdict` | `--results`, or `--blocked <reason>` to print a blocked verdict line for a run that stopped early; with `--blocked`, nothing in the results folder is read or written |
| `pr` | `--repo`, `--core`, `--feature`, `--results`, `--summary`, `--type`, `--scope`, `--why`, `--final` |
| `spend` | `--since <ISO time>`, `--from <dir>`, `--transcripts <dir>`, `--results <dir>`, `--repo` |
| `mark` | `--results <dir>`, `--step <name>`, `--build core` or `feature`, `--path <name>`, `--folder <dir>`, then `start` or `end` |
| `runs` | `--repo` |
| `wait` | `--until '<check>'`, or `--ready url`, `line` or `command` with `--profile <file>` (and `--log <file>` for `line`), and `--port <profile port>=<build port>` once per port the build runs on in place of the profile's; `--every <seconds>`, `--within <seconds>`, `--limits <file>` |
| `launch` | `--repo`, `--core`, `--feature`, `--results`, `--previous`, `--spec`, `--record <path>`, `--final`, `--parent <plugin>/<run>` |
| `metrics import` | none |

`lighthouse spend --results <dir>` counts every transcript, subagents included, whose working folder lies inside the results folder, and reports tokens by kind (`input`, `cache_write_5m`, `cache_write_1h`, `cache_read`, `output`) per model and in total, with `tokens` the sum of all kinds, dollars from the price table the command ships (null for a model it lacks, named under `unpriced`), expired cache rewrites, minutes waiting on a person, a tool and the model, and the minutes and tokens of each marked step and path, with what falls outside any mark reported as `shared`. With `--repo` it also writes `<results>/spend.json`. `lighthouse mark` appends a timed start or end line to `<results>/marks.jsonl`; a mark's `--folder` attributes to its path every transcript started inside that folder, such as a plugin path's `claude -p` trials.

`lighthouse launch` records each run in the shared metrics store (`~/.plugin-metrics`, or `PLUGIN_METRICS_DIR`) as `run.start`, `run.end` and one run summary per run, with the verdict, the suite on both builds, every product path, and lighthouse's own spend priced at write time from its price table with the table's date as `price_date`. `--parent <plugin>/<run>` (or `PLUGIN_METRICS_PARENT`) names the run that started it, and the child session gets its own store inside the results folder. `lighthouse runs --repo <path>` reads the summaries and prints one summary: the number of runs, total and median minutes and dollars, tokens by kind, minutes per step, waiting on a person and expired cache rewrites. `lighthouse_tool/catalogue.json` describes every field, and `skills/metrics` answers how lighthouse is performing with DuckDB.

`lighthouse metrics import` moves the old `runs.jsonl` ledger from the state folder into the store once and moves the file to the Trash.

`lighthouse wait --until '<check>'` reruns a shell check every `--every` seconds (default 5) and prints ready true as soon as it passes, or ready false after `--within` seconds (default and maximum 540); the caller calls it again. With `--limits <file>` it also prints `expired`, true once the file's deadline has passed or a whole window passed with no such file, and the caller stops calling it and ends the run blocked. `lighthouse wait --ready url|line|command --profile <file>` waits for the profile's `start.ready` the same way, reading it from the profile itself: `url` requests an http or https URL without a shell and is ready on a status below 400, `line` is ready once `--log <file>` holds the line, and `command` runs the command as the profile writes it. Each `--port <profile port>=<build port>` puts the build's port in place of the profile's, as the URL's port or as each whole number equal to it in a line or command, so core and FEATURE each wait on their own server. `lighthouse launch` takes lighthouse:test's flags, refuses a results folder inside the checkout, and starts `claude -p '/lighthouse:test --child <the same flags>'` on Opus with this plugin, in bypassPermissions mode, with AskUserQuestion disallowed and from `<results>/work`, keeping the machine from idle sleep while it runs. It copies the record from `--record`, or the one beside `--spec` named like the spec with `.record.json` in place of `.md`, to `<results>/record.json`, writes `<results>/limits.json` with the run's time limits and a deadline, and stops the child at its limit with a blocked line naming it. It writes `<results>/child.json` with the child's session id, cost per model, minutes, keep-awake method and priority, writes the line it prints to `<results>/launch.json`, and prints the child's verdict line, or a blocked line naming why when the child printed none.

`lighthouse suite` reuses core's stored suite result from the state folder when core's commit, the setup and build commands, the suite object and the timeout match an earlier run, marking core `reused`, so a retest on an unmoved core never runs core's suite again; FEATURE's suite always runs. It records each build's preparation, suite and rerun minutes, and each build's passing and failing test ids when a JUnit report exists, in `<results>/suite.json`.

After each setup, build and suite step, `lighthouse suite` kills the step's process group, so a server one build's step started cannot answer the other build's suite. A process that leaves that group, such as a daemon that calls `setsid`, is not stopped.

`lighthouse worktrees` and `lighthouse suite` write `commits.json` in the results folder, holding the full core and FEATURE commits they checked out. `lighthouse retest` reads an earlier results folder's `findings.json` and `commits.json` and the profile, and prints a plan: `full`, `changed` (the files changed since the previous FEATURE commit), `retest` (the paths that failed or were unproven), `surfaces` (the profile surfaces holding a changed file) and `carried` (the passed paths on untouched surfaces). It writes the same plan, with `carried_paths` holding each carried path's entry, to `<results>/retest.json`, and copies each carried path's evidence under `<results>/previous/`. `full` is true, every previous path retests and nothing carries, when the previous FEATURE commit is not an ancestor of the FEATURE tip, the core branch moved, or the previous suite or build was blocked or it holds no paths. It refuses with exit 2, writing nothing, when `--previous` and `--results` name the same folder or the previous folder lacks a valid `findings.json` or `commits.json`, or a carried path's evidence is not a file inside the previous folder. When `<results>/retest.json` exists, `lighthouse verdict` lists as unproven every planned retest path the findings leave out, or whose evidence names no existing file in the results folder outside `previous/`.

`lighthouse execute --results <dir>` runs every acceptance line of the interphase record, read from `--record`, from the record beside `--spec`, or from `<results>/record.json`, as that line's check. It refuses with exit 2 a line that fails the acceptance-line schema, runs each line's command from the FEATURE worktree's root within the check limit, and writes one check result per run to `<results>/checks.jsonl`: exit 0 is pass, exit 1 fail, and any other exit or the limit could-not-run, with the run's output as evidence. An exact line runs once more after a fail, and a judged line runs its trials. It writes `<results>/plan.json` with each check's id, kind and trials, the neighbours, which are the profile surfaces whose `paths` cover a file changed between core and FEATURE, and `reach`, each surface's `reach` command's result on this machine. It prints `checks` and `neighbours`. With no record it still computes the neighbours, and lighthouse:test plans its paths as before.

`lighthouse contrast --foreground <colour> --background <colour> --source declared|tree|pixels` prints the WCAG contrast `ratio` to two places, `threshold` 4.5, or 3.0 with `--large`, `status`, `source`, and `reason` when it could not decide. Declared and accessibility-tree colours decide pass or fail exactly; a pixel sample within 0.3 of the threshold, or a translucent colour, is could-not-run, never a failure. It reads `#RGB`, `#RRGGBB`, `#RRGGBBAA`, `0xRRGGBB`, `0xAARRGGBB` and `rgb(r, g, b)`, and refuses any other colour with exit 2.

## What lighthouse never does

- It never fixes code and never merges.
- It never touches your checkout: both builds run in throwaway worktrees inside the results folder, and the profile commit on the FEATURE branch is its only write to the project.
- It never takes an action the profile lists as off-limits, and never adds a tool or dependency to the project.
- It never puts a credential value into output, a report or git, and never uses a production entry.
- It does no load, performance or security testing, deploys nothing and never tests against production.

## Tests

```sh
python3 -m unittest discover tests
```

The end-to-end tests in `tests/test_e2e_*.py` run full `claude -p` sessions and run only when `LIGHTHOUSE_E2E=1` is set; CI never runs them.
