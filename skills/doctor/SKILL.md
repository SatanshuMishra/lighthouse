---
name: doctor
description: Use when lighthouse profile check reports a problem with .lighthouse/profile.json, or when a person wants the lighthouse profile brought up to date with the codebase. Repairs the profile so the check passes and reports missing credentials as readiness items, changing only .lighthouse/profile.json. Takes --repo <path> and --unattended.
---

# lighthouse:doctor

Bring `.lighthouse/profile.json` in the repository `--repo` names back in line with the codebase.

## Inputs

- `--repo <path>`: the repository to repair. Default: the current working directory.
- `--unattended`: ask nothing. Treat a run that lighthouse:test invoked the same way.

`lighthouse` in this skill always means `${CLAUDE_PLUGIN_ROOT}/bin/lighthouse`: run it by that full path, written out in each command, never a `lighthouse` found on PATH, which may be an older installed copy.

Everything a run needs from lighthouse is in this skill and in what its commands print, including their refusals: never read lighthouse's own code, profile schema or README, and never run its `--help`.

## Steps

1. Run `lighthouse profile check --repo <repo>` and read the problems and upgrades in its JSON.
2. When a problem has kind `missing`, invoke lighthouse:init with the same `--repo` and `--unattended` flags, and stop.
3. Fix every other problem in `.lighthouse/profile.json` alone, reading the codebase to find what is true now:
   - `command`: replace a command that no longer resolves with the command the project now uses, from its CI, README, manifests or scripts.
   - `path`: replace a path that no longer exists with the code that now holds that surface; remove the surface when its behaviour is gone.
   - `unrecorded`: read the source file, add it to `sources`, and record whatever it changes, such as a new suite, setup, build or start command, or a new surface.
   - `malformed`, `version` or `schema`: rewrite the profile as version 1 with every required key, keeping every entry that is still true, in the shape of this complete profile for a small web app:

   ```json
   {
     "version": 1,
     "sources": ["package.json", ".github/workflows/ci.yml", "jest.config.js"],
     "setup": {"command": "npm ci"},
     "build": {"command": "npm run build"},
     "start": {"command": "PORT=4100 npm start", "ready": "http://localhost:4100/health"},
     "suite": {
       "command": "npx jest --ci --reporters=default --reporters=jest-junit",
       "junit": "junit.xml",
       "timeout_minutes": 15,
       "rerun": "npx jest --ci --reporters=default --reporters=jest-junit -t {names_regex}",
       "isolated": true
     },
     "test_data": "npm run seed loads three sample users and their notes into a local SQLite file",
     "surfaces": [
       {
         "name": "notes page",
         "kind": "web page",
         "paths": ["src/pages/notes.tsx", "src/api/notes.ts"],
         "driver": "Playwright, run with npx playwright test against http://localhost:4100/notes",
         "available": true,
         "reach": "npx playwright --version",
         "sign_in": {"method": "form", "command": "npx playwright test e2e/sign-in.spec.ts"},
         "credentials": ["NOTES_TEST_EMAIL", "NOTES_TEST_PASSWORD"],
         "trials": 1
       }
     ],
     "credentials": {
       "file": null,
       "names": {
         "NOTES_TEST_EMAIL": {"production": false},
         "NOTES_TEST_PASSWORD": {"production": false}
       }
     },
     "facts": {
       "port": {"value": 4100, "confirmed": true, "recheck": "read PORT in the start script of package.json"},
       "mail service": {"value": "a local mail catcher on port 1025", "confirmed": false, "recheck": "read the SMTP settings in src/config.ts"}
     },
     "off_limits": ["sending email to real addresses", "writing to the shared staging database"]
   }
   ```

   - upgrades: write each field it names. Always write both `suite.rerun` and `suite.isolated`, reading the suite's runner and its test setup:
     - `suite.rerun`: the command run instead of the whole suite to rerun only the failing tests, from the repository root, writing the same JUnit report as `suite.command`. lighthouse replaces `{tests}` with the failing test ids (classname.name) and `{names_regex}` with a regular expression matching their names, shell-quoting each value itself, so leave each placeholder unquoted. For unittest, `python3 -m unittest {tests}` through the same runner and report options as `suite.command`; for pytest, `suite.command` plus `--lf`; for jest and vitest, `suite.command` plus `-t {names_regex}`; for go test, `suite.command` plus `-run {names_regex}`; null for any runner without a way to select failures.
     - `suite.isolated`: true only when the suite uses no fixed ports, shared databases or shared folders, so core's and FEATURE's suites may run at the same time; otherwise false.
     - `measured`: write nothing by hand; the `lighthouse profile measure` run in step 4 records the durations. Before it runs, give each surface that has no `reach` a command that exits 0 when this machine can drive the surface with its driver, such as `npx playwright --version` or `vmlab capabilities --json`.
4. Run `lighthouse profile check --repo <repo>` again. When it still fails, stop and report every remaining problem, so a caller treats the profile as blocked. When it passes and step 1 listed the `measured` upgrade, or after any repair in step 3, run `lighthouse profile measure --repo <repo>`, with the Bash tool's timeout set to 600000 ms. It runs the suite, the start command, the readiness check and each surface's `reach` command once, records their durations in the profile's `measured` object and sets each surface's `available` from its `reach` command's exit, writing no file but `.lighthouse/profile.json`.
5. Run `lighthouse credentials check --repo <repo>`. Report each missing or empty name as a readiness item, naming the file it belongs in and never a value.
6. For each surface whose `sign_in` records a command, run it through `lighthouse with-credentials --repo <repo> --sign-in <the surface's position in the profile's surfaces, counted from 0>`, which runs the recorded command as the profile writes it, so no profile text is copied into a shell line. Pass no `--profile`: lighthouse then reads the profile at the root of the repository `--repo` is in, the one doctor just checked. Report a sign-in that fails as a readiness item for that surface. Never print, ask for or accept a credential value.

## Asking

- With `--unattended`, or when lighthouse:test invoked it, ask nothing.
- When a person invoked it directly, it may ask unconfirmed facts in one round and store each answer with `lighthouse answer --repo <repo> --set <fact>=<value>`, never a credential value.

## Never

- Change only `.lighthouse/profile.json`. Never change the project's code, tests, configuration or anything outside `.lighthouse/profile.json` and lighthouse's own state folder, `~/.lighthouse/<repository folder>/`.
- Never add a tool or dependency to the project.
- Never take an action the profile lists as off-limits.
