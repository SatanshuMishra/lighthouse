# retest-what-changed: S4: lighthouse retests only what changed since the previous results
Status: parked
Updated: 2026-10-17T00:41:00.179Z
Next ids: c6 D5 R4 S2

## Goal

Build the handed-off spec docs/specs/retest-what-changed.md through the pipeline full lane from stage 2: results folders record their commits, a lighthouse retest verb plans a later run and copies carried passes, lighthouse verdict refuses green when a planned retest was skipped, lighthouse:test takes --previous, version 0.2.0; ship one MSP pull request into the FEATURE branch.

## Done when

- [x] c1 The MSP pull request is open into the FEATURE branch, ready for review and assigned to the owner, with the glossary terms Previous results and Carried path shipped in it evidence: https://github.com/SatanshuMishra/lighthouse/pull/7 is open from mitosis/retest into feat/retest-what-changed, ready for review, assigned to SatanshuMishra, with commit 5f80f5f adding the Previous results and Carried path glossary terms and the review notes comment posted
- [x] c2 Every confirmed blocker is fixed with a receipt test, or the pull request is a draft naming the blocker at the top because a diagnosis classed it blocked by a named constraint evidence: Round-1 blockers C1, C2, C3, S2, S3 were each diagnosed fixable by a fresh Opus agent and fixed with receipt tests that failed first; round 2 validator marked P1-P5 fixed and pipeline verdict printed green with no blocker
- [x] c3 The thread is parked with the next step saying the owner starts Integration by saying the MSP pull request merged evidence: park_thread set Status parked with the next step saying the owner starts Integration by saying the MSP pull request https://github.com/SatanshuMishra/lighthouse/pull/7 merged
- [x] c4 lighthouse:test has run on feat/retest-what-changed against main and opened the FEATURE pull request, with every failure diagnosed and fixed or diagnosed blocked, and the live end-to-end surface reported unproven evidence: lighthouse verdict printed green with no failures, so no fix round ran; the four Claude Code skill paths are listed unproven because they need live claude -p sessions behind LIGHTHOUSE_E2E=1; FEATURE pull request https://github.com/SatanshuMishra/lighthouse/pull/8 is open from feat/retest-what-changed into main, ready for review and assigned to SatanshuMishra
- [x] c5 The thread is parked with the next step saying the owner starts Clean-up by saying the FEATURE pull request merged evidence: park_thread sets Status parked with the next step saying the owner starts Clean-up by saying the FEATURE pull request https://github.com/SatanshuMishra/lighthouse/pull/8 merged

## Where things stand

Done: PR #7 and FEATURE PR #8 merged into main at d54e10e, and pipeline clean removed every run branch, worktree, run folder and spec file, keeping nothing.

## Next step

None: the thread closes.

## Decisions in force

## Open risks


## Settled, do not reopen

- S1 Integration tested with an unpublished copy of the owner's draft profile; no profile was committed.

## Where the details live

- Shipped code: main at d54e10e in SatanshuMishra/lighthouse (PR #7 and PR #8)
- Review ledger: ~/.mitosis/lighthouse/findings.jsonl
