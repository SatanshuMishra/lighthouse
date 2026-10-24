# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T06:22:47.628Z
Next ids: c4 D1 R1 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [ ] c1 The spec is approved by the user at interphase's read-back
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

interphase:feature is grounding (Phase 3), slug lighthouse-faster-cheaper; receipts answers are drafted.

## Next step

Finish grounding, then ask the intent round; copy the receipts answers to ~/.mitosis/lighthouse/lighthouse-faster-cheaper/receipts-answers.json before the first frontier round.

## Decisions in force

## Open risks

## Settled, do not reopen

## Where the details live

- Live-run analysis: 25 runs 2026-10-16 to 2026-10-24, about $803 API-equivalent; scripts in session scratchpad d048cfb3
- Run home: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/
- Spec files: docs/specs/lighthouse-faster-cheaper.* in the checkout
- Receipts draft: /var/folders/tz/b798spt96sjfyy924nf0cw4c0000gn/T/tmp.DJPmb5YLy8/answers.json
