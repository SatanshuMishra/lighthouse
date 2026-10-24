# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T06:20:43.948Z
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

Draft receipts answers in /var/folders/tz/b798spt96sjfyy924nf0cw4c0000gn/T/tmp.DJPmb5YLy8 (receipts init --agent output in agent.json there), then invoke interphase:feature with Interview me first; save answers as <home>/receipts-answers.json once the slug exists.

## Decisions in force

## Open risks

## Settled, do not reopen

## Where the details live

- Live-run analysis: 25 runs 2026-10-16 to 2026-10-24, about $803 API-equivalent; scripts in session scratchpad d048cfb3
- Run home: ~/.mitosis/lighthouse/<slug>/ once interphase names the slug
