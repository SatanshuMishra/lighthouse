# hr-lighthouse-executor: Run 4 of the harness-redesign program: lighthouse executes locked K1 lines and computes its verdict from K3 results
Status: parked
Updated: 2026-10-28T19:10:52.701Z
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

The FEATURE branch feat/hr-lighthouse-executor holds the CI fix (lighthouse#21) and the 60 locked tests at b9eabdc, each failing at f4da7f7 through accept.zsh; the receipt-lock line is in receipts-lock.txt. Integration runs: the MSP pull request https://github.com/SatanshuMishra/lighthouse/pull/22 is merged, so feat/hr-lighthouse-executor is at 77aad0e, integration-ready reports ready, and the integration worktree ~/.mitosis/runs/lighthouse/hr-lighthouse-executor/integration holds 77aad0e. The FEATURE suite runs there under Python 3.15 and 3.9 into <run home>/integration-suite, and lighthouse:test run 1 (installed lighthouse 0.4.0) tests main against FEATURE into <run home>/lighthouse/run-1. Review was green at round 5 with every advisory fixed. The ship's reconcile exit 6 names only the glossary and ADR commit, the fix-pass files and ledger_import.py as undeclared writes, and the locked tests (written before the build) plus tests/test_retest.py and tests/test_skill_init_doctor.py as declared but unwritten. review/report-notes.txt holds what goes only to the final report.

## Next step

Read lighthouse:test run 1's last JSON line and the FEATURE suite results under both Pythons; on green or an opened FEATURE pull request, bind it with Auto-fix on, park the thread for Clean-up and update run 4's row in PROGRAM.md; on failures or blocked, record them as integration round 1 findings and send each fixable kind to a fresh fix agent with a receipt test first.

Needs: D2.

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
