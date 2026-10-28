# hr-lighthouse-executor: Run 4 of the harness-redesign program: lighthouse executes locked K1 lines and computes its verdict from K3 results
Status: active
Updated: 2026-10-28T14:51:10.005Z
Next ids: c7 D2 R4 S1

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

The FEATURE branch feat/hr-lighthouse-executor holds the CI fix (lighthouse#21) and the 60 locked tests at b9eabdc, each failing at f4da7f7 through accept.zsh; the receipt-lock line is in receipts-lock.txt. The MSP executor is on mitosis/executor at 7effa35 (worktree ~/.mitosis/runs/lighthouse/hr-lighthouse-executor/trees/executor). Round 4's blocker U1 (failing test under Python 3.9) is fixed there: kill_tree sends the group kill even after the leader is reaped; the receipt was red at 078fff4 under both Pythons and passes, the selecting check is empty under both, the locked files are untouched, and there is no stash and no trailer. An automated commit security check flags that change (MEDIUM): a group kill after the leader is reaped can reach an unrelated group if the step's group was already empty and its id reused. The reviewer briefs go out unchanged, so the flag reaches review only if the security reviewer finds it; otherwise it goes to the final report. At 7effa35 all 60 locked checks pass (O4) and the full suite passes under Python 3.15 and 3.9 (420 tests, 3 skipped each), kept together as round 5's suite file. Review round 5 judges the fix diff from 078fff4 and has no blocker: two LOW advisory candidates, C1 (gone_by and ended_by in tests/test_process_tree.py duplicate one poll loop) and S1 (launch.stopped_output's group gets a second SIGKILL after it is reaped, which could reach a reused id; not reproduced). The candidates file carries no blocker: pipeline never carries a suite finding such as round 4's U1 but measures it again from each round's suite (tool.py carried_blockers), and both suites pass at 7effa35. The validator judges both candidates. review/report-notes.txt holds what goes only to the final report.

## Next step

When the round 5 validator reports, save its array, then run record and verdict for round 5.

Needs: D1.

## Decisions in force

- D1 interphase hand-off: build the spec as one MSP of 7 Steps with 60 locked K1 lines: Hand off now: one MSP executor with 7 Steps, 60 K1 lines and 27 assumptions; the next step is the O2 check author on feat/hr-lighthouse-executor.

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
