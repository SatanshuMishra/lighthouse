# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T06:20:30.813Z
Next ids: c4 D1 R1 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [ ] c1 The spec is approved by the user at interphase's read-back
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

Not started.

## Next step

Set up receipts in a scratch folder, then invoke interphase:feature with the request followed by Interview me first.

## Decisions in force

## Open risks

## Settled, do not reopen

## Where the details live

- Live-run analysis: 25 runs 2026-10-16 to 2026-10-24, about $803 API-equivalent; scripts in session scratchpad d048cfb3
- Run home: ~/.mitosis/lighthouse/<slug>/ once interphase names the slug
