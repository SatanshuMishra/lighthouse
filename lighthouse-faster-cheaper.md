# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T06:32:33.457Z
Next ids: c4 D1 R1 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [ ] c1 The spec is approved by the user at interphase's read-back
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

interphase:feature interview: intent I1-I4 and the shape (four pull requests) are approved and recorded. Run-3's 23.5 hours held 314 silent minutes, 194 of them waiting on an owner AskUserQuestion answer. Probes on Claude Code 2.1.308: a context: fork skill gets a fresh context but no Agent tool; a plugin agent with experimental.cacheTtl 1h and model sonnet writes 1h cache on sonnet, while 30 of 30 sampled ordinary subagents wrote 5m only; a subagent has no Agent tool, so drivers can only be dispatched from a top-level session; claude -p --output-format json reports costUSD per model and the 1h/5m cache split. Frontier round 1 is asked.

## Next step

Record the owner's round 1 answers to the decisions file and the record, run check_record.py, then ask the next frontier round.

## Decisions in force

## Open risks

## Settled, do not reopen

## Where the details live

- Live-run analysis: 25 runs 2026-10-16 to 2026-10-24, about $803 API-equivalent; scripts in session scratchpad d048cfb3
- Run home: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/
- Spec files: docs/specs/lighthouse-faster-cheaper.* in the checkout
- Receipts answers: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/receipts-answers.json
