# lighthouse-metrics: Lighthouse metrics on the shared plugin-metrics store
Status: active
Updated: 2026-10-26T23:24:39.934Z
Next ids: c5 D1 R1 S1

## Goal

Lighthouse records metrics personalised to its purpose (proving a FEATURE branch before it merges) in the shared ~/.plugin-metrics JSON Lines store through a word-for-word copy of the pipeline's reference writer, with its own catalogue, run summary carrying only its own spend, a small self-query skill, and a one-time import of ~/.lighthouse/<repo>/runs.jsonl with the retired files moved to ~/.Trash.

## Done when

- [ ] c1 The spec, decisions file, record and items for lighthouse-metrics are in docs/specs/ and the read-back is approved under the owner's delegation
- [ ] c2 The FEATURE branch is pushed and the run home ~/.mitosis/lighthouse/lighthouse-metrics/ holds CHARTER.md, worker-rules.txt, dispatch.zsh and run.zsh, with accept.zsh in the repository
- [ ] c3 run.zsh --plan-only passes with no fatal finding
- [ ] c4 The build runs once the shared reference writer exists on origin/feat/unified-metrics or origin/main, and the rest of pipeline:run reaches the last pull request

## Where things stand

Not started.

## Next step

Invoke pipeline:run and carry the full lane through Stage 1, then interphase's interview with the owner's delegated answers.

## Decisions in force

## Open risks

## Settled, do not reopen

## Where the details live

- Pipeline spec (format description until the writer lands): /Users/satanshumishra/Documents/DevLabs/pipeline/docs/specs/unified-metrics.md
- Pipeline decisions with intent I1 to I6: /Users/satanshumishra/Documents/DevLabs/pipeline/docs/specs/unified-metrics.decisions.md
- Run home: ~/.mitosis/lighthouse/lighthouse-metrics/
