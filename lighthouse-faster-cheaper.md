# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T19:17:35.516Z
Next ids: c4 D9 R5 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [x] c1 The spec is approved by the user at interphase's read-back evidence: owner chose Approve at the read-back; docs/specs/lighthouse-faster-cheaper.record.json status handed-off, check_record --complete, check_spec and check_items pass
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

Ship. faster-command and faster-skills are reviewed green at round 4 with every advisory fixed; wait --ready and with-credentials --sign-in take a repeatable `--port <profile port>=<build port>`, which step 6 passes per build. By D7 the live held-out measurement is skipped, so criterion 5.21 ships unproven and faster-held-out, holding no commits of its own, ships nothing; CHARTER.md tells Lane 5 to return ok without live runs. The glossary and ADRs 0006 to 0008 are committed in faster-command (640880c) and carried up the stack (head 66ef28c on faster-skills and faster-held-out). The comments are saved as review/<msp>.comment.md, and promote added nothing. `SHIP=1 run.zsh --resume` is running (output in the run home's ship.out and ship.err); the latest anchor is `Pipeline anchor: lighthouse-faster-cheaper at /Users/satanshumishra/.mitosis/lighthouse/lighthouse-faster-cheaper, thread lighthouse-faster-cheaper: SHIP=1 /Users/satanshumishra/.mitosis/lighthouse/lighthouse-faster-cheaper/run.zsh --resume`. A suite started as a zsh `&` job runs niced and fails test_launch_records_cost_and_priority, so suites run only as harness background tasks. SatanshuMishra/pipeline#15 (the pipeline plugin reading spend.json) is open and awaits the owner's merge.

## Next step

Run SHIP=1 /Users/satanshumishra/.mitosis/lighthouse/lighthouse-faster-cheaper/run.zsh --resume, read mitosis's JSON result for each pushed MSP's branch, base, title and body, then open the pull requests in stack order through GitHub MCP, assign each to the owner and post review/<msp>.comment.md on it.

Needs: D2, D7, D8.

## Decisions in force

- D2 first build: three stacked MSPs cut by layer: Recut by layer into three stacked MSPs, command (all lighthouse_tool changes and their unit tests), skills (skill and agent text, README), held-out (harness, baseline and comparison); plan 3 MSPs in 1 cluster of depth 3.
- D3 interphase hand-off: first build labels the MSPs faster-command, faster-skills, faster-held-out: MSPs are faster-command, faster-skills and faster-held-out with the subject 'make lighthouse:test fast and cheap'; the layer cut of D2 stands.
- D6 amendment 1 hand-off: five Steps on faster-skills-amend-1, faster-held-out resumes on the amended tasks: Build amendment 1 with amend-1.zsh (--no-push, plan-only first) into mitosis/faster-skills. Then set Lane 5's uncommitted patch aside (it is saved as held-out-1/worktree.patch) and merge mitosis/faster-skills into mitosis/faster-held-out. Add to CHARTER.md that the held-out-baseline and held-out-compare tasks in the spec's items file govern where a brief differs. Then run one resume.
- D7 owner skips the live held-out measurement; live runs measure success: The owner chose to skip the measurement and continue: faster-held-out ships nothing, criterion 5.21 is reported unproven, and faster-command and faster-skills ship as stacked pull requests.
- D8 ship: push faster-command and faster-skills as stacked pull requests: Run SHIP=1 run.zsh --resume, then open each pushed MSP's pull request through GitHub MCP in stack order, assign it to the owner and post its saved comment.

## Open risks


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
- Pull request comments per MSP: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/review/<msp>.comment.md
