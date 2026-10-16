# lighthouse

lighthouse is a Claude Code plugin that proves a FEATURE branch of any kind of software works before it merges into its core branch: the project's own suite on both branches, the running product used the way a person or calling program uses it, and the surfaces next to the change. It reports a verdict with evidence, never fixes anything, and opens the FEATURE pull request when the verdict is green or the run is marked final.

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
| `lighthouse:test` | `--repo <path>`, `--core <branch>`, `--feature <branch>`, `--results <dir>`, `--spec <path>` when a spec exists, `--final` | Tests the FEATURE branch against the core branch and ends with the verdict line. |

Only init and doctor, when a person invokes them directly, ask anything, and only questions about facts, never a credential value. lighthouse:test never asks and runs them with `--unattended`.

## The profile

`.lighthouse/profile.json` in the repository under test describes how to build, start, reach, sign into and test the project. It is the only thing lighthouse writes into a project: lighthouse:test commits a new or changed profile to the FEATURE branch as its own commit, so it is reviewed in the FEATURE pull request.

| Field | Holds |
|---|---|
| `version` | 1 |
| `sources` | the repository-relative manifest, CI and test-configuration files it was built from |
| `suite` | `command`, run from the repository root; `junit`, a JUnit XML path or null; `timeout_minutes`, a number or null |
| `surfaces` | each way the product is used: `name`, `kind`, `paths`, `driver`, `available`, `sign_in` (`method` none, command, token or form, and `command`), `credentials` (names only) and `trials` (1, or 3 when model-backed or random) |
| `credentials` | `file`, the project's own gitignored credentials file or null; `names`, each mapped to `{"production": true or false}` |
| `facts` | each name mapped to `value`, `confirmed` and `recheck` |
| `off_limits` | plain-language actions lighthouse must never take |
| `setup`, `build`, `start`, `test_data` | optional: install, build and start commands, `start.ready`, and how test data is made |

## Credentials

Credential values live in `~/.lighthouse/<repository folder>/credentials.env`, mode 0600, readable by its owner alone, or in the project's own gitignored file when the profile names one. The repository folder is the name of the folder holding the repository's main working tree. Put test accounts only there, typed by you: a name the profile marks production is refused. The profile records names, never values. Only `lighthouse with-credentials` reads the values and puts them into a child process, redacting them from its output, so no value ever appears in the chat, a report or any lighthouse output.

## Readiness and answers

`lighthouse readiness` lists the open items before an unattended run: a missing profile, each unconfirmed fact without a stored answer, and each credential name absent or empty in the credentials file. `lighthouse answer` stores fact answers in `~/.lighthouse/<repository folder>/answers.json`, and `lighthouse profile publish` folds them into the profile on the FEATURE branch.

## Verdicts

`lighthouse verdict` computes the verdict from `findings.json`; the skill never writes one.

| Verdict | When |
|---|---|
| `blocked` | the suite is blocked, or FEATURE would not build or start |
| `failures` | a suite failure, or a path that failed and failed again on retry (for a neighbour, while passing on core) |
| `unproven` | every new-behaviour path is unproven, including when none was found |
| `green` | otherwise |

A failure that passes on retry, or a case that passes some but not every trial, is flaky, never a failure. Anything not reached is unproven, never passed.

## The verdict line

The last line lighthouse:test prints is one JSON object on one line, the contract with any caller:

```json
{"verdict": "green", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "pr": "https://github.com/owner/repo/pull/1"}
```

`pr` is the pull request's URL, or null when none was opened.

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
| `with-credentials` | `--repo`, `--profile`, `--cwd <dir>`, `-- <command>` |
| `worktrees` | `--repo`, `--core`, `--feature`, `--results` |
| `suite` | `--repo`, `--core`, `--feature`, `--results`, `--profile` |
| `release` | `--repo`, `--results` |
| `verdict` | `--results` |
| `pr` | `--repo`, `--core`, `--feature`, `--results`, `--summary`, `--type`, `--scope`, `--why`, `--final` |
| `spend` | `--since <ISO time>`, `--from <dir>`, `--transcripts <dir>` |

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
