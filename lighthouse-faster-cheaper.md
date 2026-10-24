# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T07:57:30.824Z
Next ids: c4 D5 R3 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [x] c1 The spec is approved by the user at interphase's read-back evidence: owner chose Approve at the read-back; docs/specs/lighthouse-faster-cheaper.record.json status handed-off, check_record --complete, check_spec and check_items pass
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

Stage 2: the first mitosis build is running in the background, writing build-1.log; its Lane 0 Worker (session 1 of 4 of MSP faster-command) is building, and the other MSPs wait on it. Branches are mitosis/faster-command, mitosis/faster-skills and mitosis/faster-held-out stacked on feat/lighthouse-faster-cheaper (which holds the receipts config commit 480f500). Uncommitted in the checkout and shipping with the first pull request: GLOSSARY.md (six new terms), docs/adr/0006 and 0007. Parallel session pipeline-lh-spend (local_c8953839-fc6f-4338-a7c3-a2d73dd68f86) is changing the pipeline plugin to read <results>/spend.json and report dollars; it is in its review round 1, diagnosing two confirmed blockers, with no pull request yet.

## Next step

Read the last stdout line of ~/.mitosis/lighthouse/lighthouse-faster-cheaper/build-1.log when the first build finishes, write each lane's Assumption notes to review/<msp>.assumptions.txt, then start Stage 3 review round 1 for MSPs faster-command, faster-skills and faster-held-out.

Needs: D2, D3, D4, R1, R2.

## Decisions in force

- D2 first build: three stacked MSPs cut by layer: Recut by layer into three stacked MSPs, command (all lighthouse_tool changes and their unit tests), skills (skill and agent text, README), held-out (harness, baseline and comparison); plan 3 MSPs in 1 cluster of depth 3.
- D3 interphase hand-off: first build labels the MSPs faster-command, faster-skills, faster-held-out: MSPs are faster-command, faster-skills and faster-held-out with the subject 'make lighthouse:test fast and cheap'; the layer cut of D2 stands.
- D4 interphase hand-off: start the first build in a clean run directory: Start a fresh first build of items with MSPs faster-command, faster-skills and faster-held-out.

## Open risks

- R1 The held-out set starts each session fresh, so the launcher's extra child start-up may cancel the savings there and criterion 5.21's below-baseline totals could fail on small fixtures even though real pipeline runs save. Bears on c2.
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
