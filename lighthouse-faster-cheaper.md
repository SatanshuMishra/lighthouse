# lighthouse-faster-cheaper: Make lighthouse:test runs faster and cheaper without lowering test quality, and improve its metrics
Status: active
Updated: 2026-10-24T07:23:31.483Z
Next ids: c4 D1 R1 S1

## Goal

Cut lighthouse:test wall time and token spend on live pipeline runs while keeping integration-test quality, with no caps that limit project size or change width; fit each test to what the change needs; and record metrics that show where future runs spend time and tokens.

## Done when

- [ ] c1 The spec is approved by the user at interphase's read-back
- [ ] c2 The MSP pull requests are open, reviewed green or opened as drafts with their blockers
- [ ] c3 Integration's lighthouse run opens the FEATURE pull request

## Where things stand

interphase:feature interview: intent I1-I4 and the shape (four pull requests) are approved and recorded. Run-3's 23.5 hours held 314 silent minutes, 194 of them waiting on an owner AskUserQuestion answer. Probes on Claude Code 2.1.308: a context: fork skill gets a fresh context but no Agent tool; a plugin agent with experimental.cacheTtl 1h and model sonnet writes 1h cache on sonnet, while 30 of 30 sampled ordinary subagents wrote 5m only; a subagent has no Agent tool, so drivers can only be dispatched from a top-level session; claude -p --output-format json reports costUSD per model and the 1h/5m cache split. Round 1 (Q1-Q19) answered "Yes to all", with Q18 widened: out-of-scope elements may change when the audit's issues need it, other plugins in a parallel session. Recorded: decisions, three seams, criteria 5.1-5.18, 13 Steps in MSPs metrics, suite, tokens, checks. Found: all 3 AskUserQuestion calls in lighthouse runs came from lighthouse:test's main thread (557 minutes, one offered to narrow macOS scope); the VM throttle was the pipeline session's own taskpolicy -b and a keep-vms-background.zsh script, not vmlab; install/build was 18 minutes over 25 runs, so build reuse stays out. Round 2 (vmlab, never ask, keep awake, priority, held-out measuring) is asked; launcher, driver-agent and held-out criteria wait on it.

Round 2 answered and recorded (Q23: inherit priority as industry standard, record it). check_record --complete passes: criteria 5.1-5.22, 17 Steps. Glossary gained Child session, Driver agent, Check, Mark, Ledger, Expired rewrite. The read-back was approved; the run is autonomous from here. Parallel session pipeline-lh-spend (local_c8953839-fc6f-4338-a7c3-a2d73dd68f86) is changing the pipeline plugin to read <results>/spend.json and report dollars.

## Next step

interphase Phase 8: copy the feature template to docs/specs/lighthouse-faster-cheaper.md, fill it, write each Step's task into the record, render, then Phases 9 and 10, then pipeline Stage 2.

## Decisions in force

## Open risks

## Settled, do not reopen

## Where the details live

- Live-run analysis: 25 runs 2026-10-16 to 2026-10-24, about $803 API-equivalent; scripts in session scratchpad d048cfb3
- Run home: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/
- Spec files: docs/specs/lighthouse-faster-cheaper.* in the checkout
- Receipts answers: ~/.mitosis/lighthouse/lighthouse-faster-cheaper/receipts-answers.json
