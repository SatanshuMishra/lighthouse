# The launcher alone records each run in the shared metrics store

Status: accepted

lighthouse records every lighthouse:test run in the metrics store the pipeline and its plugins share, through a word-for-word copy of the pipeline's reference writer, and only lighthouse launch writes there: run.start before the child session starts, run.end after it ends, and one run summary whose spend is every message of the results folder's transcripts plus the caller's own turns between those two events, priced at that moment from the dated price table. The child session gets a store inside its results folder and no parent, so nothing a product or plugin under test records reaches the owner's store, and the per-repository ledger runs.jsonl is retired after a one-time import that moves it to the Trash.

## Considered options

- The child's own commands writing events: they run in the child's session, so one run's lines would carry two sessions, and each command would need the run id and the real store passed in.
- Keeping the ledger beside the store: two homes for one run's record, and the ledger is never pruned.
- Pricing from the child session's own reported cost: it carries no price table date and would give a run two dollar figures.
- Importing the ledger automatically at the next launch: a test run would move the owner's files as a side effect.
