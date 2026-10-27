---
name: metrics
description: Use when someone asks how lighthouse is performing, how its runs went, what lighthouse runs cost, or where lighthouse's time goes. Answers from lighthouse's records in the shared plugin-metrics store with DuckDB SQL, citing the figures, the runs in scope and the period they span.
---

# lighthouse:metrics

Answer questions about lighthouse from the records lighthouse launch writes to the shared plugin-metrics store, with the duckdb command and SQL. Metrics only report what happened; they never judge or recommend.

## Rules

- Never read Claude Code transcripts, under ~/.claude/projects or anywhere else. Every figure comes from the store.
- usd is lighthouse's own spend, every message of the run counted once: the child session, its drivers and trial sessions, and the caller's own turns between run.start and run.end, priced at write time with the price table's date in price_date. caller reports the caller's part on its own; a parent such as the pipeline leaves that span out of its own spend, so usd summed over a run tree counts each message once.
- A null means unknown. Never count a null as zero: say the figure is unknown, or how many runs it is unknown for.
- Order runs and state periods by started, never by the envelope ts. An imported summary's ts is the time of the import, not of the run.

## 1. Check for duckdb

Run `command -v duckdb`. When duckdb is not on PATH, say that the duckdb command-line tool is missing, give the install command `brew install duckdb`, and stop.

## 2. Find the store

The store root is the value of PLUGIN_METRICS_DIR when it is set and non-empty, otherwise ~/.plugin-metrics. Below, `<root>` is that folder's absolute path. lighthouse's part of the store is `<root>/plugin=lighthouse`. Write `<root>`, and any repository folder name, only inside SQL string literals in single quotes with every ' doubled, and never into a shell string.

## 3. Read the catalogue first

Read `<root>/plugin=lighthouse/catalogue.json` before writing any SQL. It states lighthouse's purpose and objectives, describes every event and summary field with its description and reading, and holds named queries, each with the question it answers. Pick the fields that answer the question from their description and reading.

## 4. Start the session

DuckDB prints times in local time unless told otherwise, so every session starts with:

```sql
SET TimeZone = 'UTC';
```

Each duckdb invocation is a fresh session: put the SET, both views and the query in one invocation, passed on standard input through a quoted heredoc so the SQL needs no shell escaping:

```
duckdb -json <<'SQL'
SET TimeZone = 'UTC';
...the two views...
...the query...
SQL
```

## 5. Define the views events and summaries

DuckDB refuses a glob that matches no file, as right after lighthouse metrics import and before any launch, when the store holds summaries and no event file. So check each part first:

```
duckdb -json <<'SQL'
SELECT count(*) AS files FROM glob('<root>/plugin=lighthouse/kind=event/**/*.jsonl');
SELECT count(*) AS files FROM glob('<root>/plugin=lighthouse/kind=summary/**/*.json');
SQL
```

When a part holds at least one file, define its view over the files. When it holds none, define its view as the empty select with the same columns below.

The events view over the files:

```sql
CREATE VIEW events AS SELECT * FROM read_json('<root>/plugin=lighthouse/kind=event/**/*.jsonl', format = 'newline_delimited', hive_partitioning = true, union_by_name = true) WHERE plugin = 'lighthouse';
```

The events view when no event file exists yet:

```sql
CREATE VIEW events AS SELECT NULL::BIGINT AS v, NULL::TIMESTAMPTZ AS ts, NULL::VARCHAR AS plugin, NULL::VARCHAR AS plugin_version, NULL::VARCHAR AS kind, NULL::VARCHAR AS event, NULL::VARCHAR AS run, NULL::VARCHAR AS parent, NULL::VARCHAR AS session, NULL::VARCHAR AS repo, NULL::VARCHAR AS core, NULL::VARCHAR AS feature, NULL::VARCHAR AS results, NULL::BOOLEAN AS retest, NULL::BOOLEAN AS final, NULL::BOOLEAN AS spec, NULL::VARCHAR AS verdict, NULL::BIGINT AS child_exit, NULL::DOUBLE AS run_seconds WHERE false;
```

The summaries view over the files:

```sql
CREATE VIEW summaries AS SELECT * FROM read_json('<root>/plugin=lighthouse/kind=summary/**/*.json', format = 'newline_delimited', hive_partitioning = true, union_by_name = true) WHERE plugin = 'lighthouse';
```

The summaries view when no summary file exists yet:

```sql
CREATE VIEW summaries AS SELECT NULL::BIGINT AS v, NULL::TIMESTAMPTZ AS ts, NULL::VARCHAR AS plugin, NULL::VARCHAR AS plugin_version, NULL::VARCHAR AS kind, NULL::VARCHAR AS event, NULL::VARCHAR AS run, NULL::VARCHAR AS parent, NULL::VARCHAR AS session, NULL::VARCHAR AS repo, NULL::TIMESTAMPTZ AS started, NULL::TIMESTAMPTZ AS ended, NULL::DOUBLE AS run_seconds, NULL::VARCHAR AS verdict, NULL::VARCHAR AS reason, NULL::VARCHAR AS core, NULL::VARCHAR AS feature, NULL::VARCHAR AS core_commit, NULL::VARCHAR AS feature_commit, NULL::BOOLEAN AS retest, NULL::BOOLEAN AS final, NULL::BOOLEAN AS spec, NULL::BIGINT AS failures, NULL::BIGINT AS unproven, NULL::BIGINT AS flaky, NULL::JSON AS build, NULL::JSON AS suite, NULL::JSON AS paths, NULL::DOUBLE AS usd, NULL::DATE AS price_date, NULL::JSON AS tokens, NULL::BIGINT AS messages, NULL::JSON AS models, NULL::JSON AS unpriced, NULL::JSON AS steps, NULL::JSON AS drives, NULL::JSON AS shared, NULL::JSON AS caller, NULL::JSON AS waiting, NULL::JSON AS expired_rewrites, NULL::BIGINT AS child_exit, NULL::VARCHAR AS child_session, NULL::VARCHAR AS results, NULL::VARCHAR AS spend_scope, NULL::BOOLEAN AS imported WHERE false;
```

When the question names a repository, add `AND repo = '<repository folder name>'` to the WHERE of each view over files, where the repository folder name is the last part of the repository's path, written with every ' doubled.

## 6. Run the queries

Run the catalogue's named query whose question matches, its sql used as written, or write your own SQL over events and summaries when none matches. Nested fields such as suite, paths, steps and drives are read the way the named queries read them, through from_json(to_json(...)) and unnest. Also run a query for the runs in scope and their period:

```sql
SELECT count(*) AS runs, min(started) AS first_started, max(started) AS last_started FROM summaries;
```

## 7. Answer

Answer with the figures, the number of runs in scope and the period they span, from the first started to the last started, in UTC. Name the repository when the answer covers one, and say which figures are unknown because their value is null. Say when spend_scope is results for some runs: those were imported from the old ledger and count only the results folder's transcripts up to the spend step.
