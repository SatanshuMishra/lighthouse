# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T07:46:27.478Z
Next ids: c4 D5 R3 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [x] c1 The spec is approved by the user at interphase's read-back evidence: owner chose Approve at the read-back; docs/specs/lighthouse-faster-cheaper.record.json status handed-off, check_record --complete, check_spec and check_items pass
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

interphase:feature interview: intent I1-I4 and the shape (four pull requests) are approved and recorded. Run-3's 23.5 hours held 314 silent minutes, 194 of them waiting on an owner AskUserQuestion answer. Probes on Claude Code 2.1.308: a context: fork skill gets a fresh context but no Agent tool; a plugin agent with experimental.cacheTtl 1h and model sonnet writes 1h cache on sonnet, while 30 of 30 sampled ordinary subagents wrote 5m only; a subagent has no Agent tool, so drivers can only be dispatched from a top-level session; claude -p --output-format json reports costUSD per model and the 1h/5m cache split. Round 1 (Q1-Q19) answered "Yes to all", with Q18 widened: out-of-scope elements may change when the audit's issues need it, other plugins in a parallel session. Recorded: decisions, three seams, criteria 5.1-5.18, 13 Steps in MSPs metrics, suite, tokens, checks. Found: all 3 AskUserQuestion calls in lighthouse runs came from lighthouse:test's main thread (557 minutes, one offered to narrow macOS scope); the VM throttle was the pipeline session's own taskpolicy -b and a keep-vms-background.zsh script, not vmlab; install/build was 18 minutes over 25 runs, so build reuse stays out. Round 2 (vmlab, never ask, keep awake, priority, held-out measuring) is asked; launcher, driver-agent and held-out criteria wait on it.

Round 2 answered and recorded (Q23: inherit priority as industry standard, record it). check_record --complete passes: criteria 5.1-5.22, 17 Steps. Glossary gained Child session, Driver agent, Check, Mark, Ledger, Expired rewrite. The read-back was approved; the run is autonomous from here. Parallel session pipeline-lh-spend (local_c8953839-fc6f-4338-a7c3-a2d73dd68f86) is changing the pipeline plugin to read <results>/spend.json and report dollars.

## Next step

Read the last stdout line of ~/.mitosis/lighthouse/lighthouse-faster-cheaper/build-1.log when the first build finishes, write each lane's Assumption notes to review/<msp>.assumptions.txt, then start Stage 3 review round 1 for MSPs faster-command, faster-skills and faster-held-out.

Needs: D2, D3, R1, R2.

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
