# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T15:44:51.230Z
Next ids: c4 D7 R5 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [x] c1 The spec is approved by the user at interphase's read-back evidence: owner chose Approve at the read-back; docs/specs/lighthouse-faster-cheaper.record.json status handed-off, check_record --complete, check_spec and check_items pass
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

Stage 3. faster-command is green at round 4 (head 08a8ed2, reviewed green), with advisory C2 (test class below the unittest.main block) fixed in 75758f3; it has no slow checks. faster-skills is green at round 4 (head 0ced454, reviewed green, base 75758f3), with advisory C3 (duplicated profile read-or-refuse) fixed in febeeda; it has no slow checks; wait --ready and with-credentials --sign-in take a repeatable `--port <profile port>=<build port>`, which step 6 passes per build. A suite started as a zsh `&` job runs niced and fails test_launch_records_cost_and_priority, so suites run only as harness background tasks. The run is stopped on a hard failure, with nothing pushed: faster-held-out (holding mitosis/faster-skills at febeeda) is still uncommitted after its one `run.zsh --resume`, because Lane 5's Worker would not start the live baseline (`python3 -m tests.measure_held_out` against d54e10e, writing tests/held_out_baseline.json) or the live `test_held_out_fixtures` pass: each is one process of a seed session plus 24 live sessions, and a Worker's commands run only in the foreground and are killed after 10 minutes. Its harness and acceptance tests are already on the branch and pass. Going on needs the owner's say. The latest anchor is `Pipeline anchor: lighthouse-faster-cheaper at /Users/satanshumishra/.mitosis/lighthouse/lighthouse-faster-cheaper, thread lighthouse-faster-cheaper: /Users/satanshumishra/.mitosis/lighthouse/lighthouse-faster-cheaper/run.zsh --resume`. Held-out pass 1: baseline d54e10e 73.1 min and $28.53 over 24 sessions, branch 111.4 min and $46.75. Branches mitosis/faster-command, mitosis/faster-skills and mitosis/faster-held-out are stacked on feat/lighthouse-faster-cheaper (receipts config 480f500), none pushed. Uncommitted in the checkout and shipping with the first pull request: GLOSSARY.md, docs/adr/0006 to 0008. SatanshuMishra/pipeline#15 (the pipeline plugin reading spend.json) is open and awaits the owner's merge.

## Next step

Report the hard failure to the owner and wait for their choice: run the live baseline and held-out pass from the main session in the background and commit the baseline to faster-held-out, then review it from round 1 and ship; or another way they name.

Needs: D2, D3, D6, R2.

## Decisions in force

- D2 first build: three stacked MSPs cut by layer: Recut by layer into three stacked MSPs, command (all lighthouse_tool changes and their unit tests), skills (skill and agent text, README), held-out (harness, baseline and comparison); plan 3 MSPs in 1 cluster of depth 3.
- D3 interphase hand-off: first build labels the MSPs faster-command, faster-skills, faster-held-out: MSPs are faster-command, faster-skills and faster-held-out with the subject 'make lighthouse:test fast and cheap'; the layer cut of D2 stands.
- D6 amendment 1 hand-off: five Steps on faster-skills-amend-1, faster-held-out resumes on the amended tasks: Build amendment 1 with amend-1.zsh (--no-push, plan-only first) into mitosis/faster-skills. Then set Lane 5's uncommitted patch aside (it is saved as held-out-1/worktree.patch) and merge mitosis/faster-skills into mitosis/faster-held-out. Add to CHARTER.md that the held-out-baseline and held-out-compare tasks in the spec's items file govern where a brief differs. Then run one resume.

## Open risks

- R2 A held-out pass is 24 live sessions; the baseline Step and the final comparison each spend real money and hours, and run-to-run variation can move a single total either way. Bears on c2.
- R3 Lane 5's resumed Worker may follow its frozen brief (the absolute per-case bar, a four-key baseline) over the charter's pointer to the amended tasks; if it ends uncommitted, the rules make it a hard failure, which stops the run before any push. Bears on c2.
- R4 The per-fixture bar against main is the amendment's own reading. It departs from the owner's round 2 answer (decision record 0004 holds on both runs) only for the cases main itself fails, and noise in two runs per fixture can fail an unchanged branch, which sends drivers back to Opus. Bears on c2.

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
- Review files per round (diffs, suites, findings, candidates, verdicts, briefs, readable records): ~/.mitosis/lighthouse/lighthouse-faster-cheaper/review/round-<n>/
- Amendment 1 build: amend-1.zsh, amend-1.items.json and amend-1.build.out/err in the run home; mitosis run directory ~/.mitosis/runs/lighthouse/lighthouse-faster-cheaper-amend-1/
- Manual gate of amendment 1: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/review/faster-skills-amend-1.manual-gate.txt
- Security-touching readings for the final report: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/review/final-report.security.md
