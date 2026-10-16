# A committed per-project profile replaces any fixed ruleset

lighthouse ships no list of project kinds, tools or rules. Each project carries .lighthouse/profile.json, written by lighthouse:init from the codebase and maintained by lighthouse:doctor, recording how to build, start, reach and test that project and which tool drives each surface, preferring the project's own tests and scripts. A new or changed profile is committed to the FEATURE branch as its own commit, the only thing lighthouse writes into a project, so the owner reviews it in the FEATURE pull request.
