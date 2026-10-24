---
name: init
description: Use when a repository has no lighthouse profile, or when lighthouse:test or lighthouse:doctor finds it missing. Reads the codebase and writes .lighthouse/profile.json, describing how to set up, build, start, reach, sign into and test the project, so lighthouse can test any kind of software without a ruleset. Takes --repo <path> and --unattended.
---

# lighthouse:init

Write `.lighthouse/profile.json` in the repository `--repo` names, from what the codebase itself says.

## Inputs

- `--repo <path>`: the repository to profile. Default: the current working directory.
- `--unattended`: ask nothing. Treat a run that lighthouse:test invoked the same way.

`lighthouse` in this skill always means `${CLAUDE_PLUGIN_ROOT}/bin/lighthouse`: run it by that full path, written out in each command, never a `lighthouse` found on PATH, which may be an older installed copy.

Everything a run needs from lighthouse is in this skill and in what its commands print, including their refusals: never read lighthouse's own code, profile schema or README, and never run its `--help`.

## Steps

1. Run `lighthouse profile check --repo <repo>`. When it exits 0, the profile already exists and passes: change nothing and report that it is healthy.
2. Read the codebase: its manifests, CI workflows, test configuration, README, scripts, entry points and its own end-to-end tests or drive scripts. Record every manifest, CI and test-configuration file you read in `sources`, as repository-relative paths.
3. Write the profile as version 1 JSON with an indent of 2, holding:
   - `version`: 1.
   - `sources`: every file read in step 2.
   - `suite`: `command`, the command the project's CI or README uses to run its tests, run from the repository root; `junit`, the repository-relative JUnit XML path when the project already writes one, otherwise null; `timeout_minutes`, a number when CI states one, otherwise null; and always both `rerun` and `isolated`:
     - `suite.rerun`: the command run instead of the whole suite to rerun only the failing tests, from the repository root, writing the same JUnit report as `suite.command`. lighthouse replaces `{tests}` with the failing test ids (classname.name) and `{names_regex}` with a regular expression matching their names, shell-quoting each value itself, so leave each placeholder unquoted. For unittest, `python3 -m unittest {tests}` through the same runner and report options as `suite.command`; for pytest, `suite.command` plus `--lf`; for jest and vitest, `suite.command` plus `-t {names_regex}`; for go test, `suite.command` plus `-run {names_regex}`; null for any runner without a way to select failures.
     - `suite.isolated`: true only when the suite uses no fixed ports, shared databases or shared folders, so core's and FEATURE's suites may run at the same time; otherwise false.
   - `setup`: `command` that installs dependencies in a fresh checkout, when the project needs one.
   - `build`: `command`, when the product builds.
   - `start`: `command` and `ready`, a URL, log line or command that shows the product is up, when the product runs.
   - Leave `setup`, `build` or `start` out of the profile entirely when the project has no such step. Never write one with a null, empty or placeholder field: each field it holds is a string.
   - `surfaces`: one entry for every way a person or calling program uses the product, such as each command, page or flow, endpoint group, public module, skill or device feature. Give each:
     - `name` and `kind`, in plain words.
     - `paths`: the repository-relative code paths behind it.
     - `driver`: the tool and how it drives this surface. Choose the project's own end-to-end tests, drive scripts or runner first; otherwise an industry-standard tool used without adding anything to the project.
     - `available`: false when this machine cannot reach it, such as hardware, a platform or a service this machine lacks; otherwise true.
     - `sign_in`: `method` none when no sign-in is needed; otherwise prefer the project's own sign-in command or fixture (`command`), then a token request to the project's own API (`token`), then a web form filled by a Playwright script run under `lighthouse with-credentials` (`form`). Put the shell command in `command`, or null for none.
     - `credentials`: the credential names it needs, never their values.
     - `trials`: 3 when the surface's output comes from a model or from randomness, otherwise 1.
   - `credentials`: `file`, the repository-relative path of the project's own gitignored test-credentials file when one exists, otherwise null; `names`, every credential name a surface needs, each mapped to `{"production": true}` when the entry is a production or live account and `{"production": false}` otherwise.
   - `facts`: everything not certain from the code, such as ports, URLs, accounts, services and environment, each with `value`, `confirmed` and `recheck` (how to re-check it). Mark every fact you cannot confirm from the codebase `confirmed: false`.
   - `off_limits`: every outward-facing action not confirmed safe, in plain language, such as sending email or messages, taking payments, and writing to shared or production services.
   - `test_data`, when the project documents how test data is made.

   A complete profile for a small web app, holding every field above:

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
4. When any surface needs signing in, run `lighthouse credentials init --repo <repo>`. It creates the credentials file with empty values, or uses the project's own file.
5. Run `lighthouse profile check --repo <repo>`. When it reports problems, fix each once in the profile and run the check once more. When it still fails, stop and report every remaining problem, so a caller treats the profile as blocked.

## Asking

- With `--unattended`, or when lighthouse:test invoked it, ask nothing. Unconfirmed facts stay `confirmed: false`.
- When a person invoked it directly, ask the unconfirmed facts in one round, and store each answer with `lighthouse answer --repo <repo> --set <fact>=<value>`.
- Never ask for, accept or write a credential value. Values go only into the file `lighthouse credentials init` names, typed by the person themselves.
- When a person invoked it directly, tell them `.lighthouse/profile.json` is written for them to review and commit.

## Never

- Never change the project's code, tests or configuration; write only `.lighthouse/profile.json`.
- Never add a tool or dependency to the project.
- Never take an action the profile lists as off-limits.
