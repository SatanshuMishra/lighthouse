# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T06:23:44.806Z
Next ids: c4 D1 R1 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [ ] c1 The spec is approved by the user at interphase's read-back
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

interphase:feature interview: the intent round (goal, why, success, shape) is asked and awaits the owner's answer. Docs say skills can run with context: fork, plugins can ship agents with a model and experimental.cacheTtl 1h, subagents can nest three deep, and claude -p loads installed plugins; none of this is run-verified yet.

## Next step

Record the owner's intent answers as I1-I3 in docs/specs/lighthouse-faster-cheaper.decisions.md, then ask the first frontier round.

## Decisions in force

## Open risks

## Settled, do not reopen

## Where the details live

- Live-run analysis: 25 runs 2026-10-16 to 2026-10-24, about $803 API-equivalent; scripts in session scratchpad d048cfb3
- Run home: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/
- Spec files: docs/specs/lighthouse-faster-cheaper.* in the checkout
- Receipts answers: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/receipts-answers.json
