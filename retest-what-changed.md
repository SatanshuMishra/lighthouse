# retest-what-changed: S4: lighthouse retests only what changed since the previous results
Status: active
Updated: 2026-10-16T21:52:36.337Z
Next ids: c4 D3 R3 S1

## Goal

Build the handed-off spec docs/specs/retest-what-changed.md through the pipeline full lane from stage 2: results folders record their commits, a lighthouse retest verb plans a later run and copies carried passes, lighthouse verdict refuses green when a planned retest was skipped, lighthouse:test takes --previous, version 0.2.0; ship one MSP pull request into the FEATURE branch.

## Done when

- [ ] c1 The MSP pull request is open into the FEATURE branch, ready for review and assigned to the owner, with the glossary terms Previous results and Carried path shipped in it
- [ ] c2 Every confirmed blocker is fixed with a receipt test, or the pull request is a draft naming the blocker at the top because a diagnosis classed it blocked by a named constraint
- [ ] c3 The thread is parked with the next step saying the owner starts Integration by saying the MSP pull request merged

## Where things stand

MSP retest is committed on mitosis/retest (head dfa32cb, base feat/retest-what-changed at 2e00295) in worktree ~/.mitosis/runs/lighthouse/retest-what-changed/trees/retest; the full suite passes there on 3.14 and 3.9. Round 1 outcome is loop (review/round-1/retest.md). Confirmed blockers in three classes: rename hides changed file (C1), skipped retest judged green (C2, S2, S3), retest name mismatch (C3). Advisories C4, C5, S4. Three fresh Opus diagnosis agents, one per class, are running.

## Next step

When the three diagnoses return, fix each class classed fixable on mitosis/retest in the worktree with a receipt test that fails first and one class-wide change, fix advisories C4, C5 and S4, commit naming the ids, and start review round 2.

Needs: D2, R1.

## Decisions in force

- D2 Interphase hand-off: build S4 as one MSP from the handed-off retest-what-changed spec: Build MSP retest on feat/retest-what-changed with the installed mitosis 0.5.0 and lighthouse 0.1.0; fill later gaps from I1-I4 as recorded assumptions.

## Open risks

- R1 Items copy in the run home tags every Step with msp retest so the four Steps ship as one MSP, as the decisions file requires; the spec's own items file would split into four MSPs. Bears on c1.
- R2 GLOSSARY.md holds the uncommitted terms Previous results and Carried path in the owner's checkout; Workers build from the committed state and the terms ship in a separate glossary commit at Ship. Bears on c1.

## Settled, do not reopen

## Where the details live

- Spec: /Users/satanshumishra/Documents/DevLabs/lighthouse/docs/specs/retest-what-changed.md (decisions, record and items beside it)
- Run home: ~/.mitosis/lighthouse/retest-what-changed/
- Run dir: ~/.mitosis/runs/lighthouse/retest-what-changed
- Review ledger: ~/.mitosis/lighthouse/findings.jsonl
- Review round files and worker assumptions: ~/.mitosis/lighthouse/retest-what-changed/review/
