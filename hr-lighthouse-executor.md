# hr-lighthouse-executor: Run 4 of the harness-redesign program: lighthouse executes locked K1 lines and computes its verdict from K3 results
Status: active
Updated: 2026-10-28T15:15:05.611Z
Next ids: c7 D3 R4 S1

## Goal

Run 4 of the harness-redesign program (~/.mitosis/harness-redesign/PROGRAM.md, logbook thread harness-redesign in the pipeline repository): make lighthouse compute its verdict from K3 check results only, execute an interphase record's K1 lines as its paths, bound every wait by measured durations, measure contrast without pixel guesses, probe the profile at init, and open the FEATURE pull request on an unproven verdict in the same run. Full lane, overrides O1 to O10 applied by hand.

## Done when

- [ ] c1 L1 The verdict is computed from K3 check results only: a passed path whose evidence file is missing, a new path that failed once without a retry, a check that passed 2 of 3 trials, and a suite result that differs from suite.json each make the verdict not green.
- [ ] c2 L2 With a record holding K1 lines, lighthouse executes those lines as its paths, each path id equal to its check id, plus neighbours computed by code from the changed files.
- [ ] c3 L3 The child session, the suite and the run each have a time limit taken from durations measured at init.
- [ ] c4 L4 Contrast is measured from declared colours or the accessibility tree where available; a pixel sample within 0.3 of a threshold is could-not-run, never a failure.
- [ ] c5 L5 lighthouse init runs the suite, the start command, the readiness check and each driver once and records their durations; available is read by code.
- [ ] c6 L6 An unproven verdict opens the FEATURE pull request in the same run, listing what could not be reached; no second run exists only to add --final.

## Where things stand

The FEATURE branch feat/hr-lighthouse-executor holds the CI fix (lighthouse#21) and the 60 locked tests at b9eabdc, each failing at f4da7f7 through accept.zsh; the receipt-lock line is in receipts-lock.txt. The MSP executor is on mitosis/executor at 7effa35 (worktree ~/.mitosis/runs/lighthouse/hr-lighthouse-executor/trees/executor), and its review verdict is green at round 5: no blocker, every earlier advisory fixed by its fix commits, all 60 locked checks passing (O4) and the full suite passing under Python 3.15 and 3.9 (420 tests, 3 skipped each, none of them an acceptance test, so no slow check needs a rerun). The validator rejected round 5's S1 (a second group SIGKILL after reap reaching a reused id) as unreachable: the second kill met no process, and wrapping the PID space takes about 154 s against a 5 s window; the automated commit check's MEDIUM flag on the same change goes to the final report with that result. The one confirmed advisory, C1 (a duplicated poll loop in tests/test_process_tree.py), is fixed on the branch at bcece7f, and the glossary terms and ADRs 0007, 0010 and 0011 are committed on top at d40a570 (docs only, with a receipts ack), the head to ship; the worktree is clean with no stash, no trailer and the locked files untouched. The O4 locked checks and both suites run at d40a570 into review/ship-o4. origin/feat/hr-lighthouse-executor contains origin/main. The pull request comment is saved as review/executor.comment.md (the receipt-lock line and the 14 assumptions), and promote added no do-not-flag kind. review/report-notes.txt holds what goes only to the final report.

## Next step

When review/ship-o4 shows 60 locked checks and both suites passing, record the ship boundary, then run SHIP=1 run.zsh --resume --proven-head executor=d40a570 and open, assign and comment the pull request.

Needs: D1.

## Decisions in force

- D1 interphase hand-off: build the spec as one MSP of 7 Steps with 60 locked K1 lines: Hand off now: one MSP executor with 7 Steps, 60 K1 lines and 27 assumptions; the next step is the O2 check author on feat/hr-lighthouse-executor.
- D2 ship boundary: ship executor at d40a570 as one ready pull request: Ship now: SHIP=1 run.zsh --resume --proven-head executor=d40a570, then open the pull request ready for review, assigned to the owner, with review/executor.comment.md as its comment.

## Open risks

- R1 Locked acceptance test files sit in their Steps' write-sets because interphase's items format requires it; only worker rules, the receipts lock hash and the locked checks at each MSP head keep a Worker from loosening them. Bears on c1.
- R2 A repository whose tests pin its root entries fails once .lighthouse/profile.json is first committed on FEATURE; lighthouse reports that as a suite failure rather than hiding it. Bears on c5.
- R3 The suite runs so far used Python 3.15, which hides failures the CI's Python 3.9 shows; every head's suite now runs under both, and a 3.9-only failure is a suite finding. Bears on c3.

## Settled, do not reopen

## Where the details live

- Program: /Users/satanshumishra/.mitosis/harness-redesign/PROGRAM.md (run 4 of 7; intent I1 to I6, contracts K1 to K7, overrides O1 to O10)
- Audit: /Users/satanshumishra/.mitosis/harness-redesign/audit/lighthouse.md
- Contracts: /Users/satanshumishra/.mitosis/harness-redesign/contracts/ (k1-acceptance, k2-locked, k3-check-result, k6-outcome)
- Spec, decisions, record, items: /Users/satanshumishra/Documents/DevLabs/lighthouse/docs/specs/hr-lighthouse-executor.*
- Run home: /Users/satanshumishra/.mitosis/lighthouse/hr-lighthouse-executor/ (acceptance.jsonl holds the 60 K1 lines; check-author-brief.md the check authors' brief; CHARTER.md the Workers' charter and locked list; receipts-lock.txt the lock line; build-1.txt the first build's output; items.json, run.zsh, dispatch.zsh, worker-rules.txt)
- Mitosis run directory: /Users/satanshumishra/.mitosis/runs/lighthouse/hr-lighthouse-executor
- Review folder: <run home>/review (round-<n>/ diffs, suites, briefs and findings; executor.assumptions.txt; executor.obligations.md)
