---
name: doctor
description: Use when lighthouse profile check reports a problem with .lighthouse/profile.json, or when a person wants the lighthouse profile brought up to date with the codebase. Repairs the profile so the check passes and reports missing credentials as readiness items, changing only .lighthouse/profile.json. Takes --repo <path> and --unattended.
---

# lighthouse:doctor

Bring `.lighthouse/profile.json` in the repository `--repo` names back in line with the codebase.

## Inputs

- `--repo <path>`: the repository to repair. Default: the current working directory.
- `--unattended`: ask nothing. Treat a run that lighthouse:test invoked the same way.

Run the lighthouse command as `lighthouse` when it is on PATH, otherwise as `${CLAUDE_PLUGIN_ROOT}/bin/lighthouse`.

## Steps

1. Run `lighthouse profile check --repo <repo>` and read the problems in its JSON.
2. When a problem has kind `missing`, invoke lighthouse:init with the same `--repo` and `--unattended` flags, and stop.
3. Fix every other problem in `.lighthouse/profile.json` alone, reading the codebase to find what is true now:
   - `command`: replace a command that no longer resolves with the command the project now uses, from its CI, README, manifests or scripts.
   - `path`: replace a path that no longer exists with the code that now holds that surface; remove the surface when its behaviour is gone.
   - `unrecorded`: read the source file, add it to `sources`, and record whatever it changes, such as a new suite, setup, build or start command, or a new surface.
   - `malformed`, `version` or `schema`: rewrite the profile as version 1 with every required key, keeping every entry that is still true.
4. Run `lighthouse profile check --repo <repo>` again. When it still fails, stop and report every remaining problem, so a caller treats the profile as blocked.
5. Run `lighthouse credentials check --repo <repo>`. Report each missing or empty name as a readiness item, naming the file it belongs in and never a value.
6. For each surface whose `sign_in` records a command, run it through `lighthouse with-credentials --repo <repo> -- /bin/sh -c '<the surface's sign_in command>'`, since the command is a shell command. Pass no `--profile`: lighthouse then reads the profile at the root of the repository `--repo` is in, the one doctor just checked. Report a sign-in that fails as a readiness item for that surface. Never print, ask for or accept a credential value.

## Asking

- With `--unattended`, or when lighthouse:test invoked it, ask nothing.
- When a person invoked it directly, it may ask unconfirmed facts in one round and store each answer with `lighthouse answer --repo <repo> --set <fact>=<value>`, never a credential value.

## Never

- Change only `.lighthouse/profile.json`. Never change the project's code, tests, configuration or anything outside `.lighthouse/profile.json` and lighthouse's own state folder, `~/.lighthouse/<repository folder>/`.
- Never add a tool or dependency to the project.
- Never take an action the profile lists as off-limits.
