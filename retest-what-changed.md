# retest-what-changed: S4: lighthouse retests only what changed since the previous results
Status: active
Updated: 2026-10-16T22:19:39.571Z
Next ids: c4 D4 R4 S1

## Goal

Build the handed-off spec docs/specs/retest-what-changed.md through the pipeline full lane from stage 2: results folders record their commits, a lighthouse retest verb plans a later run and copies carried passes, lighthouse verdict refuses green when a planned retest was skipped, lighthouse:test takes --previous, version 0.2.0; ship one MSP pull request into the FEATURE branch.

## Done when

- [ ] c1 The MSP pull request is open into the FEATURE branch, ready for review and assigned to the owner, with the glossary terms Previous results and Carried path shipped in it
- [ ] c2 Every confirmed blocker is fixed with a receipt test, or the pull request is a draft naming the blocker at the top because a diagnosis classed it blocked by a named constraint
- [ ] c3 The thread is parked with the next step saying the owner starts Integration by saying the MSP pull request merged

## Where things stand

MSP retest lives on mitosis/retest (base feat/retest-what-changed at 2e00295) in worktree ~/.mitosis/runs/lighthouse/retest-what-changed/trees/retest, head 159c369. Round 1 (head dfa32cb) was loop; all three blocker classes were diagnosed fixable and every round-1 blocker and advisory (C1, C2, C3, S2, S3, C4, C5, S4) is fixed there with receipt tests that failed first. Round 2 at head 159c369: the full suite passes (128 tests on 3.14 and 3.9) code-reviewer found one LOW smell (C1, duplicated containment check in retest.py) and no new defect; security-reviewer found one LOW (S1, any existing results-folder file counts as fresh evidence). The validator is judging 5 carried blockers (P1-P5) and the two LOW advisories.

## Next step

When the round-2 validator returns, save its array as review/round-2/retest.verdicts.json, run pipeline record and verdict, and fix any advisory it confirms before ship.

Needs: D2, R1.

## Decisions in force

- D2 Interphase hand-off: build S4 as one MSP from the handed-off retest-what-changed spec: Build MSP retest on feat/retest-what-changed with the installed mitosis 0.5.0 and lighthouse 0.1.0; fill later gaps from I1-I4 as recorded assumptions.
- D3 Ship boundary: push MSP retest and open its pull request into feat/retest-what-changed: Ship now as one ready-for-review pull request from mitosis/retest into feat/retest-what-changed, assigned to the owner, with the review notes comment.

## Open risks

- R1 Items copy in the run home tags every Step with msp retest so the four Steps ship as one MSP, as the decisions file requires; the spec's own items file would split into four MSPs. Bears on c1.
- R2 GLOSSARY.md holds the uncommitted terms Previous results and Carried path in the owner's checkout; Workers build from the committed state and the terms ship in a separate glossary commit at Ship. Bears on c1.
- R3 The C1 fix changes lighthouse_tool/change.py, which no MSP Step owns and the spec lists as Reused as is; the pull request must name it under risk and the assumption is in review/retest.assumptions.txt. Bears on c1.

## Settled, do not reopen

## Where the details live

- Spec: /Users/satanshumishra/Documents/DevLabs/lighthouse/docs/specs/retest-what-changed.md (decisions, record and items beside it)
- Run home: ~/.mitosis/lighthouse/retest-what-changed/
- Run dir: ~/.mitosis/runs/lighthouse/retest-what-changed
- Review ledger: ~/.mitosis/lighthouse/findings.jsonl
- Review round files and worker assumptions: ~/.mitosis/lighthouse/retest-what-changed/review/
