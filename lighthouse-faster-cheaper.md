# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T12:30:16.883Z
Next ids: c4 D6 R3 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [x] c1 The spec is approved by the user at interphase's read-back evidence: owner chose Approve at the read-back; docs/specs/lighthouse-faster-cheaper.record.json status handed-off, check_record --complete, check_spec and check_items pass
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

Stage 3 review round 1 runs for faster-command (head fe222e5, base 480f500) and faster-skills (head 5d56dc9, base fe222e5): code-reviewer, security-reviewer and conformance-auditor dispatched on each; both suites pass under Python 3.15 and 3.9; diffs, obligations, proofs and assumptions are in review/. The first build exited 10: faster-held-out is blocked because Lane 5 reported failed on criterion 5.21. Held-out pass 1: baseline d54e10e 73.1 min and $28.53 over 24 sessions, branch 111.4 min and $46.75; 5 of 24 cases fail on each side (branch H4 broken run 2 and all four H6; baseline H4 clean 1, H5 clean 1, H6 broken 1, H6 clean 1 and 2). Per case the launcher parent costs about $0.50 and the child $1.52 against the baseline's $1.19; lighthouse mark calls take 143 child turns ($6.16 over 21 children), and children read lighthouse's own code and schema in 32 turns. Lane 1's notes say it skipped the profile upgrades row and that reused core skips the build despite spec decision 7. Branches are mitosis/faster-command, mitosis/faster-skills and mitosis/faster-held-out stacked on feat/lighthouse-faster-cheaper (which holds the receipts config commit 480f500). Uncommitted in the checkout and shipping with the first pull request: GLOSSARY.md (six new terms), docs/adr/0006 and 0007. Parallel session pipeline-lh-spend (local_c8953839-fc6f-4338-a7c3-a2d73dd68f86) changed the pipeline plugin to read <results>/spend.json and report dollars; its pull request SatanshuMishra/pipeline#15 (mitosis/lighthouse-spend into feat/lighthouse-spend) is open, unmerged and awaiting the owner.

## Next step

When the six round 1 reviewers report, collect review/round-1/<msp>.findings.json for faster-command and faster-skills with their arrays plus the held-out pass 1 result as suite findings, then run pipeline candidates, the validator, record, verdict and diagnosis.

Needs: D2, D3, R1, R2.

## Decisions in force

- D2 first build: three stacked MSPs cut by layer: Recut by layer into three stacked MSPs, command (all lighthouse_tool changes and their unit tests), skills (skill and agent text, README), held-out (harness, baseline and comparison); plan 3 MSPs in 1 cluster of depth 3.
- D3 interphase hand-off: first build labels the MSPs faster-command, faster-skills, faster-held-out: MSPs are faster-command, faster-skills and faster-held-out with the subject 'make lighthouse:test fast and cheap'; the layer cut of D2 stands.
- D5 faster-held-out's one resume waits for the upstream fix pass: Held-out pass 1 goes into round 1 as suite findings on faster-command and faster-skills; faster-held-out's one resume runs after their fixes are merged into it, reusing the baseline measured at d54e10e (saved in held-out-1/).

## Open risks

- R1 The held-out set starts each session fresh, so the launcher's extra child start-up cancels the savings there: held-out pass 1 measured it, and criterion 5.21 fails until the fix pass removes the fixed overhead. Bears on c2.
- R2 A held-out pass is 24 live sessions; the baseline Step and the final comparison each spend real money and hours, and run-to-run variation can move a single total either way. Bears on c2.

## Settled, do not reopen

## Where the details live

- Live-run analysis: 25 runs 2026-10-16 to 2026-10-24, about $803 API-equivalent; scripts in session scratchpad d048cfb3
- Run home: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/
- Spec files: docs/specs/lighthouse-faster-cheaper.* in the checkout
- Receipts answers: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/receipts-answers.json
- Run scripts and charter: run.zsh, dispatch.zsh, worker-rules.txt, CHARTER.md, items.json, graph.json in the run home
- mitosis run directory: ~/.mitosis/runs/lighthouse/lighthouse-faster-cheaper/
- Probe evidence for the design (fork skill, plugin agent cache, headless background wait, AskUserQuestion disallowed, priority): the decisions file's round 1 and 2 lines
- Held-out pass 1 data (per-case baseline.jsonl and branch.jsonl, measure script, the Lane 5 worktree patch and baseline file): ~/.mitosis/lighthouse/lighthouse-faster-cheaper/held-out-1/
