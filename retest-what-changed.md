# retest-what-changed: S4: lighthouse retests only what changed since the previous results
Status: active
Updated: 2026-10-16T21:08:38.474Z
Next ids: c4 D2 R1 S1

## Goal

Build the handed-off spec docs/specs/retest-what-changed.md through the pipeline full lane from stage 2: results folders record their commits, a lighthouse retest verb plans a later run and copies carried passes, lighthouse verdict refuses green when a planned retest was skipped, lighthouse:test takes --previous, version 0.2.0; ship one MSP pull request into the FEATURE branch.

## Done when

- [ ] c1 The MSP pull request is open into the FEATURE branch, ready for review and assigned to the owner, with the glossary terms Previous results and Carried path shipped in it
- [ ] c2 Every confirmed blocker is fixed with a receipt test, or the pull request is a draft naming the blocker at the top because a diagnosis classed it blocked by a named constraint
- [ ] c3 The thread is parked with the next step saying the owner starts Integration by saying the MSP pull request merged

## Where things stand

Not started.

## Next step

Record the interphase hand-off boundary, then cut the FEATURE branch with pipeline feature-branch --type feat and write the run home ~/.mitosis/lighthouse/retest-what-changed/.

## Decisions in force

- D1 Interphase hand-off: build S4 from the handed-off retest-what-changed spec: Build the spec as one MSP on a feat FEATURE branch with the installed mitosis 0.5.0 and lighthouse 0.1.0; fill later gaps from I1-I4 as recorded assumptions.

## Open risks

## Settled, do not reopen

## Where the details live

- Spec: /Users/satanshumishra/Documents/DevLabs/lighthouse/docs/specs/retest-what-changed.md (decisions, record and items beside it)
- Run home: ~/.mitosis/lighthouse/retest-what-changed/
- Run dir: ~/.mitosis/runs/lighthouse/retest-what-changed
- Review ledger: ~/.mitosis/lighthouse/findings.jsonl
