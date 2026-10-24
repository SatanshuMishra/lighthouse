# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T14:27:53.112Z
Next ids: c4 D7 R5 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [x] c1 The spec is approved by the user at interphase's read-back evidence: owner chose Approve at the read-back; docs/specs/lighthouse-faster-cheaper.record.json status handed-off, check_record --complete, check_spec and check_items pass
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

Stage 3 fix pass after round 2. faster-command (base 480f500, round 2 head 02af478): round 2 verdict loop; both kinds diagnosed fixable and fixed with receipts first, P2 by giving its skills/test/SKILL.md stop line --repo and --results as faster-skills has it, C1 by an enclosing-checkout guard in launch.py, and advisories C2, C3, C5, C6 fixed, in commits b219e33 to ea3e27b on mitosis/faster-command; its round 3 suite waits on the faster-skills diagnoses, since unledgered blocked run lives in launch.py. faster-skills (base 02af478, round 2 head b7c4ed6, previous head 5d56dc9): amendment 1 is merged; round 2 verdict diagnose: carried P1 to P3 fixed, blockers C1 (unledgered blocked run: a refused launch writes a blocked launch.json but no ledger line, so the skill never runs Stopping early) and S1, S2 (shell quoting injection: the Command reference splices start.ready raw into the shell), advisory C4 (the reference lists dollars in a blocked line). shell quoting injection is diagnosed fixable and recorded: lighthouse wait gains --ready url|line|command reading start.ready from the profile, with-credentials gains --sign-in <n>, and the skills drop every template that splices profile text into a shell line (selecting check lists skills/test/SKILL.md:58, :60, :129 twice and skills/doctor/SKILL.md:76); the unledgered blocked run diagnosis is running. Merging faster-command into faster-skills waits for them and will conflict in spend.py, which amendment 1 rewrote (MarkedFolder became MarkLine). Amendment 1's mitosis gate shows six inconclusive test_e2e_harness_spend.py results from the old accept.zsh; the manual gate shows all 17 amendment acceptance tests pass with the work and fail reverted. CHARTER.md points Workers at the amended held-out tasks. faster-held-out (head 5d56dc9) is clean, with Lane 5's changes saved in held-out-1/, and its one resume waits for faster-skills to review green, since it spends two live held-out passes. Held-out pass 1: baseline d54e10e 73.1 min and $28.53 over 24 sessions, branch 111.4 min and $46.75; 5 of 24 cases fail on each side (branch H4 broken run 2 and all four H6; baseline H4 clean 1, H5 clean 1, H6 broken 1, H6 clean 1 and 2). Per case the launcher parent costs about $0.50 and the child $1.52 against the baseline's $1.19; lighthouse mark calls take 143 child turns ($6.16 over 21 children), and children read lighthouse's own code and schema in 32 turns. Lane 1's notes say it skipped the profile upgrades row and that reused core skips the build despite spec decision 7. Branches are mitosis/faster-command, mitosis/faster-skills and mitosis/faster-held-out stacked on feat/lighthouse-faster-cheaper (which holds the receipts config commit 480f500). Uncommitted in the checkout and shipping with the first pull request: GLOSSARY.md (seven new terms), docs/adr/0006, 0007 and 0008. Parallel session pipeline-lh-spend (local_c8953839-fc6f-4338-a7c3-a2d73dd68f86) changed the pipeline plugin to read <results>/spend.json and report dollars; its pull request SatanshuMishra/pipeline#15 (mitosis/lighthouse-spend into feat/lighthouse-spend) is open, unmerged and awaiting the owner.

## Next step

Record faster-skills' two diagnoses and retake its verdict; land any fix in launch.py on faster-command; merge mitosis/faster-command into mitosis/faster-skills and fix faster-skills' kinds and C4 there; then run round 3 for both. Once faster-skills is green, merge mitosis/faster-skills into mitosis/faster-held-out and run run.zsh --resume once.

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
