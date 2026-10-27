# lighthouse-metrics: Lighthouse metrics on the shared plugin-metrics store
Status: parked
Updated: 2026-10-27T06:27:08.920Z
Next ids: c5 D3 R3 S1

## Goal

Lighthouse records metrics personalised to its purpose (proving a FEATURE branch before it merges) in the shared ~/.plugin-metrics JSON Lines store through a word-for-word copy of the pipeline's reference writer, with its own catalogue, run summary carrying only its own spend, a small self-query skill, and a one-time import of ~/.lighthouse/<repo>/runs.jsonl with the retired files moved to ~/.Trash.

## Done when

- [x] c1 The spec, decisions file, record and items for lighthouse-metrics are in docs/specs/ and the read-back is approved under the owner's delegation evidence: docs/specs/lighthouse-metrics.{md,decisions.md,record.json,items.json} exist; check_record --complete, check_spec and check_items exit 0; record status handed-off; read-back approved under the owner's delegation and recorded in the decisions file
- [x] c2 The FEATURE branch is pushed and the run home ~/.mitosis/lighthouse/lighthouse-metrics/ holds CHARTER.md, worker-rules.txt, dispatch.zsh and run.zsh, with accept.zsh in the repository evidence: feat/lighthouse-metrics pushed to origin at e09b805; run home holds CHARTER.md, worker-rules.txt, dispatch.zsh, run.zsh, graph.json, items.json and feature.json; acceptance uses ~/.mitosis/lighthouse/accept.zsh
- [x] c3 run.zsh --plan-only passes with no fatal finding evidence: run.zsh --plan-only exit 0 (plan-3.log): 10 Steps, 7 lanes, 3 MSPs metrics-foundation, run-records, ledger-import; lane_cycles 0, no fatal finding, empty attention list
- [ ] c4 The build runs once the shared reference writer exists on origin/feat/unified-metrics or origin/main, and the rest of pipeline:run reaches the last pull request

## Where things stand

Stage 2: the first build is starting. The shared writer is on origin/feat/unified-metrics at a39ab11 (not on main), and the CHARTER's Writer source names that commit. The glossary terms and ADR 0009 are uncommitted in the checkout and ship with the first pull request.

## Next step

Run ~/.mitosis/lighthouse/lighthouse-metrics/run.zsh for the first build, then review every MSP from Stage 3 of pipeline:run, validate, fix, and ship the three MSP pull requests in stack order.

Needs: D2, R1.

## Decisions in force

- D2 interphase hand-off: first build of lighthouse-metrics from the writer at a39ab11: Build now from origin/feat/unified-metrics at a39ab11, named in the CHARTER's Writer source, then follow pipeline:run through review to the MSP pull requests.

## Open risks

- R1 The parallel spec lighthouse-proves-changes in this checkout also owns GLOSSARY.md and docs/adr and may change suite, launch and verdict; whichever merges second must rebase the other's glossary and ADR numbering and recheck run-record's launch.py and ledger-retired's verdict.py edits. Bears on c4.
- R2 5.18 (a fresh session answering from the store) and 5.20 (the live import, including macOS Trash access) are unproven until run by hand after merge. Bears on c4.

## Settled, do not reopen

## Where the details live

- Shared writer and format: origin/feat/unified-metrics of the pipeline checkout /Users/satanshumishra/Documents/DevLabs/pipeline
- Pipeline decisions with intent I1 to I6: /Users/satanshumishra/Documents/DevLabs/pipeline/docs/specs/unified-metrics.decisions.md
- Run home: ~/.mitosis/lighthouse/lighthouse-metrics/
- Spec, decisions, record, items: docs/specs/lighthouse-metrics.{md,decisions.md,record.json,items.json} in this checkout
- Read-back note: the shared side-session notes folder, lighthouse-metrics-readback.md
- Glossary and ADR: GLOSSARY.md and docs/adr/0009-the-launcher-records-each-run-in-the-shared-metrics-store.md
