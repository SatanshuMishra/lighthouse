# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: parked
Updated: 2026-10-24T19:45:45.367Z
Next ids: c4 D9 R5 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [x] c1 The spec is approved by the user at interphase's read-back evidence: owner chose Approve at the read-back; docs/specs/lighthouse-faster-cheaper.record.json status handed-off, check_record --complete, check_spec and check_items pass
- [x] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers evidence: SatanshuMishra/lighthouse#9 (faster-command, base feat/lighthouse-faster-cheaper) and #10 (faster-skills, stacked on mitosis/faster-command) are open, ready for review, assigned to SatanshuMishra and carry their review comments; both reviewed green at round 4; faster-held-out ended unchanged by D7, so it has no pull request
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

Integration run 2 is under way with the installed 0.2.0 lighthouse:test skill, results in the run home's lighthouse/run-2. lighthouse:init wrote a profile without suite.rerun and suite.isolated (the installed check refuses them), published to the FEATURE branch as 94f3222. The suite passed on both builds and every direct command check passed (evidence/direct-*.json and neighbour-*.json in run-2). The 15 live sessions (scratchpad drive_sessions.py: test:feature:1-3, init and doctor on core and feature 1-3) are running on held-out fixtures, each loading only its build's plugin copy through an enabledPlugins override; scratchpad read_sessions.py summarises them. The first 15 sessions passed on outcome (evidence/sessions-summary.json, sessions-batch1.jsonl): H1 test trials 3 of 3 name the drop bug through a launched child; init 3 of 3 per build; doctor 3 of 3 per build, two trials repairing on a branch because the owner's global pipeline rule loads into fixture sessions. Three H2 web-page trials are running to reach the lighthouse:driver agent, which H1's direct checks never dispatch. By D7 criterion 5.21 ships unproven and faster-held-out ended unchanged. mitosis's ship (output in the run home's ship.out) exited 20 because 11 acceptance tests are inert (10 in faster-command, 1 in faster-skills), and reconcile listed undeclared writes and crossings from the fix passes, amendment 1 and the glossary commit; the pull request bodies' What changed repeats "Context: lighthouse is a Claude Code plugin." per Step, a mitosis defect left unedited by rule. The latest anchor is `Pipeline anchor: lighthouse-faster-cheaper at /Users/satanshumishra/.mitosis/lighthouse/lighthouse-faster-cheaper, thread lighthouse-faster-cheaper: SHIP=1 /Users/satanshumishra/.mitosis/lighthouse/lighthouse-faster-cheaper/run.zsh --resume`. SatanshuMishra/pipeline#15 (the pipeline plugin reading spend.json) is open and awaits the owner's merge.

## Next step

Read lighthouse:test run 2's verdict line; on green report the FEATURE pull request it opened, otherwise record its failures as integration findings and fix, verdict or rerun as Integration says.

Needs: D7.

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
