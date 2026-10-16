# retest-what-changed: S4: lighthouse retests only what changed since the previous results
Status: active
Updated: 2026-10-16T22:20:58.229Z
Next ids: c4 D4 R4 S1

## Goal

Build the handed-off spec docs/specs/retest-what-changed.md through the pipeline full lane from stage 2: results folders record their commits, a lighthouse retest verb plans a later run and copies carried passes, lighthouse verdict refuses green when a planned retest was skipped, lighthouse:test takes --previous, version 0.2.0; ship one MSP pull request into the FEATURE branch.

## Done when

- [x] c1 The MSP pull request is open into the FEATURE branch, ready for review and assigned to the owner, with the glossary terms Previous results and Carried path shipped in it evidence: https://github.com/SatanshuMishra/lighthouse/pull/7 is open from mitosis/retest into feat/retest-what-changed, ready for review, assigned to SatanshuMishra, with commit 5f80f5f adding the Previous results and Carried path glossary terms and the review notes comment posted
- [x] c2 Every confirmed blocker is fixed with a receipt test, or the pull request is a draft naming the blocker at the top because a diagnosis classed it blocked by a named constraint evidence: Round-1 blockers C1, C2, C3, S2, S3 were each diagnosed fixable by a fresh Opus agent and fixed with receipt tests that failed first; round 2 validator marked P1-P5 fixed and pipeline verdict printed green with no blocker
- [ ] c3 The thread is parked with the next step saying the owner starts Integration by saying the MSP pull request merged

## Where things stand

MSP retest lives on mitosis/retest (base feat/retest-what-changed at 2e00295) in worktree ~/.mitosis/runs/lighthouse/retest-what-changed/trees/retest, head 5f80f5f. Review round 2 is green: P1-P5 fixed, advisory C1 fixed, S1 rejected at the bar. The glossary terms are committed on the branch and review/retest.comment.md holds the review notes. The SHIP=1 resume run is in progress (log ship.log in the run home).

## Next step

Open the MSP pull request from mitosis/retest (5f80f5f, pushed) into feat/retest-what-changed with create_pull_request using review/retest.title.txt and review/retest.body.md unchanged, assign it to the owner and post review/retest.comment.md.

Needs: D3, R3.

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
