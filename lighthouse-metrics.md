# lighthouse-metrics: Lighthouse metrics on the shared plugin-metrics store
Status: parked
Updated: 2026-10-27T19:04:19.787Z
Next ids: c5 D4 R3 S3

## Goal

Lighthouse records metrics personalised to its purpose (proving a FEATURE branch before it merges) in the shared ~/.plugin-metrics JSON Lines store through a word-for-word copy of the pipeline's reference writer, with its own catalogue, run summary carrying only its own spend, a small self-query skill, and a one-time import of ~/.lighthouse/<repo>/runs.jsonl with the retired files moved to ~/.Trash.

## Done when

- [x] c1 The spec, decisions file, record and items for lighthouse-metrics are in docs/specs/ and the read-back is approved under the owner's delegation evidence: docs/specs/lighthouse-metrics.{md,decisions.md,record.json,items.json} exist; check_record --complete, check_spec and check_items exit 0; record status handed-off; read-back approved under the owner's delegation and recorded in the decisions file
- [x] c2 The FEATURE branch is pushed and the run home ~/.mitosis/lighthouse/lighthouse-metrics/ holds CHARTER.md, worker-rules.txt, dispatch.zsh and run.zsh, with accept.zsh in the repository evidence: feat/lighthouse-metrics pushed to origin at e09b805; run home holds CHARTER.md, worker-rules.txt, dispatch.zsh, run.zsh, graph.json, items.json and feature.json; acceptance uses ~/.mitosis/lighthouse/accept.zsh
- [x] c3 run.zsh --plan-only passes with no fatal finding evidence: run.zsh --plan-only exit 0 (plan-3.log): 10 Steps, 7 lanes, 3 MSPs metrics-foundation, run-records, ledger-import; lane_cycles 0, no fatal finding, empty attention list
- [x] c4 The build runs once the shared reference writer exists on origin/feat/unified-metrics or origin/main, and the rest of pipeline:run reaches the last pull request evidence: built from the shared writer, reviewed green (metrics-foundation round 1, ledger-import round 2, run-records round 3), shipped by SHIP=1 run.zsh --resume with every MSP pushed and gated, and opened as SatanshuMishra/lighthouse#14, #15 and #16, assigned and commented

## Where things stand

Clean-up is done: #18 merged into main (292bb73), the run report is saved at ~/.mitosis/lighthouse/reports/lighthouse-metrics.json, and pipeline clean removed every worktree, branch, run folder and untracked spec file, keeping nothing. The live import ran once from main: 23 runs from 11 ledgers are in the store, each passing the shared check, and the 11 ledgers are in ~/.Trash as runs.jsonl and runs 2 to 13.jsonl. It refused ~/.lighthouse/.windful-ocean/runs.jsonl, left in place, because the store rejects a repo name starting with a dot. The store has no lighthouse catalogue until a reinstalled lighthouse launch runs once.

## Next step

Close this thread; the .windful-ocean ledger and the reinstall are follow-ups outside it.

Needs: R1.

## Decisions in force


## Open risks

- R1 The parallel spec lighthouse-proves-changes in this checkout also owns GLOSSARY.md and docs/adr and may change suite, launch and verdict; whichever merges second must rebase the other's glossary and ADR numbering and recheck run-record's launch.py and ledger-retired's verdict.py edits. Bears on c4.

## Settled, do not reopen

- S1 The first build ran from the shared writer at a39ab11, byte-identical on the pipeline's origin/main.
- S2 The three MSPs shipped as #14, #15 and #16 and reached feat/lighthouse-metrics through the catch-up pull request #17.

## Where the details live

- Shared writer and format: origin/main of the pipeline checkout /Users/satanshumishra/Documents/DevLabs/pipeline (the feature branch is deleted)
- Pipeline decisions with intent I1 to I6: /Users/satanshumishra/Documents/DevLabs/pipeline/docs/specs/unified-metrics.decisions.md
- Run home: ~/.mitosis/lighthouse/lighthouse-metrics/
- Spec, decisions, record, items: docs/specs/lighthouse-metrics.{md,decisions.md,record.json,items.json} in this checkout
- Read-back note: the shared side-session notes folder, lighthouse-metrics-readback.md
- Glossary and ADR: GLOSSARY.md and docs/adr/0009-the-launcher-records-each-run-in-the-shared-metrics-store.md
- Review rounds (diffs, briefs, suite output, findings, verdicts, diagnoses, comments): review/ in the run home
- Lighthouse runs (launch line, suite, marks, evidence, child session record): lighthouse/run-<k>/ in the run home
