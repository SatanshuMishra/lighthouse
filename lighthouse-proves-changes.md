# lighthouse-proves-changes: Make lighthouse fast and able to prove the changes it tests
Status: active
Updated: 2026-10-26T23:09:53.405Z
Next ids: c1 D1 R1 S1

## Goal

Resolve every issue in the 2026-10-26 lighthouse investigation report (unreachable surfaces, suite time, pre-existing labelling without names, blocked-with-nothing, the spend.json contract, the idle parent, lab contention, and new issues N1-N6), including credential onboarding in lighthouse init with a pre-formatted git-ignored credentials file, so lighthouse can prove a FEATURE branch autonomously; other repositories such as VMLab change only where lighthouse needs them and stay independent of lighthouse.

## Done when

## Where things stand

Interphase feature pathway, slug lighthouse-proves-changes, in its interview. Intent I1 to I4 is approved and recorded; frontier round 1 (Q1 to Q20: suite, credentials, lab, live sessions, verdict, contract, parent hold, speed, seams, scope) is asked and awaits the owner's answers. Grounding facts it rests on: `claude -p --setting-sources project,local --plugin-dir <build>` loads only that build's plugin under the real HOME; CLAUDE_CODE_SESSION_ATTENDED is 1 attended and 0 in claude -p; VMLab already offers status --json, up --wait and memory backoff; tmux is installed.

## Next step

Write the owner's round-1 answers to the decisions file and the agreed seams to the record, then ask the next frontier round or move to the read-back.

## Decisions in force

## Open risks

## Settled, do not reopen

## Where the details live

- Report: /private/tmp/claude-501/-Users-satanshumishra-Documents-DevLabs-lighthouse/3d733df8-fcfb-4ce9-b615-284ae9b37216/scratchpad/lighthouse-investigation-report.md
- Lane: full, run through pipeline:run 0.10.0
- Interview files: docs/specs/lighthouse-proves-changes.decisions.md (intent and decisions), .record.json (seams, criteria, Steps), .guard.json (tree guard snapshot), in the lighthouse repository
