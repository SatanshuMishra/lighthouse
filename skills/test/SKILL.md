---
name: test
description: Use when a FEATURE branch holding merged changes must be proven before it merges into its core branch, for any kind of software. Runs the project's own suite on both branches, drives the running product the way a person or calling program uses it, rechecks the surfaces next to the change, has the lighthouse command compute the verdict, and opens the FEATURE pull request on green or with --final. Takes --repo, --core, --feature, --results, --spec and --final, and ends with one JSON verdict line.
---

# lighthouse:test

Prove the FEATURE branch works: its suite, its new behaviour as used, and its neighbours. Report what was found; the lighthouse command computes the verdict.

## Inputs

- `--repo <path>`: the repository under test.
- `--core <branch>`: the core branch, the long-lived branch the repository ships from.
- `--feature <branch>`: the FEATURE branch holding the merged changes under test.
- `--results <dir>`: the results folder this run writes into.
- `--spec <path>`: the spec, when one exists.
- `--final`: open the pull request whatever the verdict, listing every failure as unresolved.

Run the lighthouse command as `lighthouse` when it is on PATH, otherwise as `${CLAUDE_PLUGIN_ROOT}/bin/lighthouse`.

## Steps

1. Note the start time as UTC ISO-8601 and the current directory as the start directory.
2. Run `lighthouse worktrees --repo <repo> --core <core> --feature <feature> --results <results>`. It checks out both tips at `<results>/core` and `<results>/feature`.
3. Run `lighthouse profile check --repo <results>/feature`.
   - When a problem has kind `missing`, invoke lighthouse:init `--unattended --repo <results>/feature`. On any other problem, invoke lighthouse:doctor `--unattended --repo <results>/feature`. Then run the check again.
   - When it still fails, record the suite as `{"result": "blocked", "reason": "profile: <problems>", "failures": [], "pre_existing": [], "flaky": [], "core": null, "feature": null}`, the build as `{"result": "blocked", "reason": "profile"}` and no paths, and go to step 8.
   - Otherwise run `lighthouse profile publish --repo <repo> --feature <feature> --profile <results>/feature/.lighthouse/profile.json`. It folds every stored answer in and commits only when the profile changed. When its JSON says `committed` is true, run `lighthouse worktrees` again with the same four flags, so `<results>/feature` moves to the new tip and holds the answered facts.
4. Run `lighthouse change --repo <repo> --core <core> --feature <feature>` for the commits, the changed files and the merged pull requests. Then run `lighthouse suite --repo <repo> --core <core> --feature <feature> --results <results> --profile <results>/feature/.lighthouse/profile.json` and keep its JSON object as the suite.
5. Plan the paths. Nothing else is tested.
   - New-behaviour paths: one product path for each thing the change adds, with its expected outcome, from the spec's intent and acceptance criteria when `--spec` is given, otherwise from the merged pull requests' titles and bodies and the commit messages.
   - Neighbours: each profile surface whose recorded `paths` include a changed file, or a file that uses something the change altered. Go one hop only. Use `graphify-out/graph.json` when the repository has one, otherwise a text search of `<results>/feature` for the altered names.
6. Build and start each build in its own worktree, `<results>/core` and `<results>/feature`, with the profile's `setup`, `build` and `start` commands, giving each build its own ports and data and setting `LIGHTHOUSE_BUILD` to `core` or `feature`. Wait for `start.ready`.
   - When FEATURE will not build or start after two tries, record the build as `{"result": "blocked", "reason": "<the failing step>; core built"}` or `"...; core did not build"`, and test no product path on it. Otherwise record `{"result": "ok", "reason": null}`.
   - Sign in only through `lighthouse with-credentials --repo <repo> --cwd <that build's worktree> -- /bin/sh -c '<the surface's sign_in command>'`.
   - A path is unproven, with its reason, when its surface is unavailable (`available` false), rests on an unconfirmed fact, needs an action the profile lists as off-limits, or cannot be signed into.
7. Drive each path with its surface's recorded `driver`, as a person or calling program would. Save every screenshot, transcript, response and output under `<results>/evidence/`, and record each as a path relative to `<results>`.
   - A new-behaviour path runs on FEATURE and is judged against the intent. Its `core` is null.
   - A neighbour gets the same probe on core and on FEATURE. A difference the intent does not explain is a failure. A difference the intent explains is expected: write that outcome as `expected`, mark it passed and note the difference in its evidence.
   - Retry each failure once on FEATURE and record the second outcome as `retry`, otherwise null. Probe a failing neighbour on core and record that as `core`.
   - When the surface's `trials` is above 1, run each case that many times on each build, graded on the outcome, never on wording. Record `trials` as `{"count": <n>, "feature_passed": <n>, "core_passed": <n or null>}`, and status passed only when every FEATURE trial passed. Otherwise `trials` is null.
8. Run `lighthouse spend --since <start time> --from <start directory>` and keep its `tokens` and `minutes`.
9. Write `<results>/findings.json`:
   ```json
   {"version": 1, "suite": <lighthouse suite's object>, "build": {"result": "ok", "reason": null},
    "paths": [{"name": "...", "kind": "new" or "neighbour", "surface": "...", "expected": "...",
               "evidence": ["evidence/..."], "status": "passed" or "failed" or "unproven",
               "retry": "passed" or "failed" or null, "core": "passed" or "failed" or null, "trials": null}],
    "spend": {"tokens": <n>, "minutes": <n>}}
   ```
   Then run `lighthouse verdict --results <results>`. It writes `report.md` and `verdict.json` and prints the verdict line. Never write or change a verdict yourself.
10. When the verdict is green, or `--final` is given, run `lighthouse pr --repo <repo> --core <core> --feature <feature> --results <results> --summary '<a lowercase summary of the feature>' --why '<the intent>'`, adding `--final` when given. When the repository's remote is on GitHub, open the pull request with its `title`, `body`, `base` and `head`, ready for review and never a draft: through the GitHub MCP `create_pull_request` tool when this session has it, otherwise `gh pr create --base <core> --head <feature> --title '<title>' --body-file <results>/pr-body.md` after writing the body there. With any other remote, open nothing and say why.
11. Run `lighthouse release --repo <repo> --results <results>`.
12. Print the verdict line from `<results>/verdict.json`, with `pr` set to the pull request's URL or null, as the last line of the reply, one JSON object on one line:
    `{"verdict": "green", "failures": [], "unproven": [], "flaky": [], "tokens": 0, "minutes": 0, "pr": null}`

## Cost

Scope comes from the change: the new-behaviour paths and their one-hop neighbours, nothing else. Each path gets one probe and at most one retry, or its trials. The project's own suite runs first, and doctor runs only when the check fails.

## Never

- Never ask anything; init and doctor run with `--unattended`.
- Never fix code, never merge, and never touch the checkout at `--repo` or anything the profile lists as off-limits. The profile commit from `lighthouse profile publish` is the only write to the project.
- Never read, print or pass a credential value; only `lighthouse with-credentials` puts values into a process.
- Never add a tool or dependency to the project.
- Never count an unreached path as passed; it is unproven.
