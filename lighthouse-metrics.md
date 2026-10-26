# lighthouse-metrics: Lighthouse metrics on the shared plugin-metrics store
Status: active
Updated: 2026-10-26T23:54:49.158Z
Next ids: c5 D2 R1 S1

## Goal

Lighthouse records metrics personalised to its purpose (proving a FEATURE branch before it merges) in the shared ~/.plugin-metrics JSON Lines store through a word-for-word copy of the pipeline's reference writer, with its own catalogue, run summary carrying only its own spend, a small self-query skill, and a one-time import of ~/.lighthouse/<repo>/runs.jsonl with the retired files moved to ~/.Trash.

## Done when

- [ ] c1 The spec, decisions file, record and items for lighthouse-metrics are in docs/specs/ and the read-back is approved under the owner's delegation
- [ ] c2 The FEATURE branch is pushed and the run home ~/.mitosis/lighthouse/lighthouse-metrics/ holds CHARTER.md, worker-rules.txt, dispatch.zsh and run.zsh, with accept.zsh in the repository
- [ ] c3 run.zsh --plan-only passes with no fatal finding
- [ ] c4 The build runs once the shared reference writer exists on origin/feat/unified-metrics or origin/main, and the rest of pipeline:run reaches the last pull request

## Where things stand

interphase Phase 9: the spec, record and items pass their checks (21 criteria, 8 Steps, 3 MSPs); one spec-reviewer pass is running. The glossary terms and ADR 0009 are written, uncommitted. The FEATURE branch feat/lighthouse-metrics is pushed at main's tip, and the run home holds CHARTER.md, worker-rules.txt, dispatch.zsh, run.zsh and graph.json; items.json is copied after the review fixes. No receipts commit is needed (receipts.config.json is committed). The shared reference writer is not yet on origin/feat/unified-metrics or origin/main.

## Next step

Apply the spec reviewer's real findings, rerender and recheck, finish interphase Phase 10 (guard verify, record handed-off), copy the items file to the run home, and run ~/.mitosis/lighthouse/lighthouse-metrics/run.zsh --plan-only until it has no fatal finding.

## Decisions in force

- D1 interphase hand-off: build lighthouse-metrics once the shared writer lands: Hand off now. The first build waits until the dependency check in the pipeline checkout prints the writer paths on origin/feat/unified-metrics or origin/main; then the CHARTER's Writer source names that ref, run.zsh runs, and pipeline:run continues to the last pull request.

## Open risks

## Settled, do not reopen

## Where the details live

- Pipeline spec (format description until the writer lands): /Users/satanshumishra/Documents/DevLabs/pipeline/docs/specs/unified-metrics.md
- Pipeline decisions with intent I1 to I6: /Users/satanshumishra/Documents/DevLabs/pipeline/docs/specs/unified-metrics.decisions.md
- Run home: ~/.mitosis/lighthouse/lighthouse-metrics/
- Spec, decisions, record, items: docs/specs/lighthouse-metrics.{md,decisions.md,record.json,items.json} in this checkout
- Read-back note: the shared side-session notes folder, lighthouse-metrics-readback.md
- Glossary and ADR: GLOSSARY.md and docs/adr/0009-the-launcher-records-each-run-in-the-shared-metrics-store.md
