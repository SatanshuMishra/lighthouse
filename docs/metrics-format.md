# Plugin metrics format

This is the format every Claude Code plugin uses to record metrics about its own work on this machine, so that one SQL query can read every plugin's records together and a plugin installed on its own can still report on itself. It is written for the author of any plugin, including one who has never seen the pipeline repository. Format version: 1.

## Purpose

Metrics collect and never judge. A stored value says what happened, such as how long a step took, what it cost, or how many attempts it needed; it never says whether that was good, and it never recommends a change. Judging is left to whoever reads the figures.

Every field names its reader and the question it answers. A field nobody reads, or one that answers no stated question, is not collected. A value that another record already holds is derived from that record when it is read, not written a second time.

## The store

The store is the one folder tree that holds every plugin's metrics files. Its root is `~/.plugin-metrics`, that is `<HOME>/.plugin-metrics`, unless the environment variable `PLUGIN_METRICS_DIR` is set and non-empty, in which case its value is the root. No plugin owns the root; each plugin writes only under its own `plugin=<plugin>` folder.

Folder names below the root are `key=value` pairs, so a query engine reads `plugin`, `kind` and `repo` straight from the path. The store holds three kinds of file.

| Path under the root | Holds | How it is written |
|---|---|---|
| `plugin=<plugin>/catalogue.json` | the plugin's catalogue | replaced whole whenever its bytes differ from the plugin's copy |
| `plugin=<plugin>/kind=event/repo=<repo>/<run>.jsonl` | one run's events, one JSON object per line | appended, one whole line per write |
| `plugin=<plugin>/kind=summary/repo=<repo>/<run>.json` | one run's single summary line | replaced whole |

Here `<plugin>` is the plugin's name, `<repo>` the repository folder's name, and `<run>` the run id. A file the writer creates has mode 0600 and a folder it creates has mode 0700, because the store holds the owner's run history. Replacing a file goes through a temporary file named `.<random>.tmp` in the same folder, renamed over the target, so a reader never sees a partial file; readers and checks skip such temporaries.

The store holds run metadata only: never prompt text, file contents or secrets.

## The envelope

The envelope is the keys every line starts with, always in this order. The line's own fields follow the envelope.

| Key | Type | Meaning |
|---|---|---|
| `v` | integer | the format version, `1` |
| `ts` | string | when the line was written, in UTC as `YYYY-MM-DDTHH:MM:SSZ` |
| `plugin` | string | the plugin that wrote the line |
| `plugin_version` | string or null | the writing plugin's version, or null when unknown |
| `kind` | string | `event` for an event line, `summary` for a run summary |
| `event` | string | the event's name from the catalogue; `run.summary` for a summary |
| `run` | string | the run id |
| `parent` | string or null | `<plugin>/<run id>` of the run that started this one, or null |
| `session` | string or null | the Claude Code session id, or null |
| `repo` | string | the repository folder's name |

The writer takes `parent` from the environment variable `PLUGIN_METRICS_PARENT` and `session` from the environment variable `CLAUDE_CODE_SESSION_ID`; each is null when its variable is unset or empty. A harness that starts another plugin's run exports `PLUGIN_METRICS_PARENT` as its own `<plugin>/<run id>`, for example `pipeline/feat-a.20261001T100000Z`, and the child's lines then name it as their parent. A plugin run on its own leaves the variable unset, so its `parent` is null.

## Run ids and names

A run is one unit of a plugin's work, named by its run id. A run id is lowercase letters, digits, dots and hyphens, starts with a letter or digit, is at most 120 characters, and may end in a `.YYYYMMDDTHHMMSSZ` start stamp, the only place an uppercase `T` or `Z` appears. It is unique per plugin per repository and never reused: a second run of the same work gets a new id.

The writer's `run_id(name, start)` (in TypeScript `runId(name, start)`) builds `<name>.<YYYYMMDDTHHMMSSZ>` from a name and the run's start, converted to UTC. For example, the pipeline names its run for the slug `feat-a` started at 2026-10-01 10:00:00 UTC `feat-a.20261001T100000Z`.

A plugin name is lowercase letters, digits and hyphens starting with a letter. A repo is the repository folder's name: never empty, at most 120 characters, never starting with a dot, and holding no slash, equals sign or control character. These rules keep every name inside its folder. The writer refuses anything else and writes nothing.

## Encoding

Each line is compact JSON in UTF-8, with no space after a comma or colon, keys in the order given, and a newline at its end. Non-ASCII characters are written as UTF-8, not escaped; only a lone surrogate is escaped as `\uXXXX`. Numbers are written as ECMAScript's `Number::toString` writes them, so the Python and TypeScript writers produce the same bytes.

| Value | Written as |
|---|---|
| a float with an integral value, such as `2.0` | `2` |
| a number from 1e-6 up to but not including 1e21 | plain decimal, such as `0.000001` or `1.5` |
| a number outside that range | exponent form, such as `1e+21` or `1.5e-7` |
| NaN or an infinity | `null` |

A field name is lowercase letters, digits and underscores starting with a letter, and is never an envelope key. No object key anywhere in a line, at any depth, is an integer string such as `"0"` or `"-12"`, because JavaScript moves integer-like keys to the front of an object and the two writers would then write different bytes. A map keyed by data, such as one entry per reviewer, is written as a list of records instead.

A catalogue is written as two-space indented JSON with a trailing newline, not as a compact line.

## Events and run summaries

An event is one line written at a boundary of a run, such as a step starting or ending. Events are appended to the run's `.jsonl` file, so the file grows by one whole line per write, and several processes may append to it at once.

A run summary is the one line per run holding its totals and its purpose-specific figures. Its `kind` is `summary` and its `event` is `run.summary`. A summary is replaced whole: writing a summary again for the same run renames a new file over the old one, so a later summary replaces the earlier and the file always holds exactly one line.

## Shared measures

A shared measure is a field whose name fixes its unit across every plugin, so figures added across plugins never mix units. Every other field is the plugin's own.

| Field name | Unit | Value |
|---|---|---|
| ends `_seconds` | seconds | a number of seconds |
| `usd`, or ends `_usd` | US dollars | a number of US dollars, priced at write time |
| `tokens`, or ends `_tokens` | tokens | an object of exactly the integer keys `input`, `cache_write_5m`, `cache_write_1h`, `cache_read` and `output`, in that order |

A `usd` figure records the date of the price table it was priced from in a field beside it, as the pipeline's `prices_date` does, so a later reader knows which prices produced it. The five token kinds are fresh input, cache writes kept five minutes, cache writes kept one hour, cache reads, and output. A model is always recorded by its exact model id, such as `claude-opus-5-5`, never by a family name.

A null value is always valid and means unknown.

## Counting cost once

A summary records only its own plugin's spend. When a plugin runs inside another run's Claude Code session, the parent leaves out of its own spend every message timed inside the child's span, from the child's first event to its last, so the same messages are never counted by both.

A whole run's cost is the sum of `usd` over its run tree: the run itself and every run reachable from it through `parent`. Adding a child's spend to its parent's summary would count it twice, so no summary does that.

A child run that has written no summary is missing, never zero. A reader adding spend over a tree reports how many runs had no summary beside the total, so a total never looks complete when it is not.

## The catalogue

A catalogue is a plugin's description of every event and field it writes. A plugin ships its catalogue and copies it to `plugin=<plugin>/catalogue.json` whenever the copy in the store differs, so a fresh reader understands each value without reading the plugin's code. Its keys:

| Key | Holds |
|---|---|
| `format` | the format version, `1` |
| `plugin` | the plugin's name |
| `purpose` | what the plugin is for, in plain words |
| `objectives` | what the plugin must achieve to serve its purpose, each with `id`, `text` and `measured_by`, a list naming `event.field` or `summary.field` for each field that measures it |
| `events` | every event, keyed by its name, each with `description`, `writer`, `readers`, `questions` and `fields` |
| `summary` | the run summary, with `description` and `fields` |
| `queries` | named queries, each with `name`, the `question` it answers and the `sql` that answers it over the store's views |

`fields` maps each field's name to a field entry. Every field entry holds these keys:

| Key | Holds |
|---|---|
| `type` | one of `integer`, `number`, `string`, `boolean`, `enum`, `object` or `array` |
| `description` | what the field records, in plain words |
| `measured_from` | how and from what it is measured |
| `unit` | one of `seconds`, `usd`, `tokens`, `count`, `ratio`, `id`, `text`, `timestamp` or `none` |
| `includes` | what the value counts |
| `excludes` | what the value leaves out |
| `reading` | how to read the value: which direction means what, and what zero or null means |
| `readers` | who reads the field |
| `question` | what the field helps answer |

An `enum` field adds `values`, the allowed values. An `object` field may add `fields`, an entry for each of its keys, and an `array` field may add `items`, one field entry describing every element; each nested entry holds the same keys. The `reading` describes and never judges: "higher means more attempts before the lane passed; 1 means it passed first time" describes, where "higher is worse" judges.

Starting from purpose and objectives means a question about whether a plugin serves its purpose leads straight to the fields in `measured_by`. The schema metrics/schema/catalogue.schema.json states the same keys, and metrics/schema/line.schema.json states the envelope of one line.

## Retention

The store stays bounded by counting runs, not days, per plugin per repository. For each plugin and repository it keeps the event files of the newest 100 runs and the summary files of the newest 1000 runs; older files are deleted. Counting runs keeps comparisons meaningful whether the work was busy or idle, where a day limit would wipe a quiet project's history after a break.

The writer prunes that plugin's folder for that repository whenever it writes a summary. A run's age is its start: the `ts` of the first line of its event file, or the summary's `ts` when it has no events; runs with the same start are ordered by run id. A prune that fails after the summary is written returns a warning and leaves the summary in place.

## Writing never raises

A metrics failure never breaks a plugin's real work. Every write returns nothing (None in Python, null in TypeScript) on success, or a warning string starting `metrics not written: ` when it refused or failed. A refusal names the subject and the rule, such as `metrics not written: run: must not be empty`; a failure names the path and the reason the system gave. The caller keeps its own exit code and output and adds only that warning.

| Python | TypeScript | Writes |
|---|---|---|
| `append_event(plugin, plugin_version, repo, run, event, fields, environ=None, now=None)` | `appendEvent({plugin, pluginVersion, repo, run, event, fields, environ?, now?})` | one event line |
| `write_summary(plugin, plugin_version, repo, run, fields, environ=None, now=None)` | `writeSummary({plugin, pluginVersion, repo, run, fields, environ?, now?})` | the run summary, then prunes |
| `write_catalogue(plugin, catalogue, environ=None)` | `writeCatalogue({plugin, catalogue, environ?})` | the catalogue, when it differs |

`environ` defaults to the process environment and `now` to the current time; passing them makes a write reproducible in a test.

## Conformance

There is no shared package to depend on. A plugin written in Python copies pipeline_tool/metrics_writer.py word for word, and a plugin written in TypeScript or JavaScript copies metrics/metrics-writer.ts word for word; each is self-contained in its language's standard library. A TypeScript copy runs directly under Node 22.18 or later, which strips the types.

Each plugin then runs the conformance fixtures in its own tests, so a copy that drifts fails there. metrics/fixtures/cases.json lists cases; each case has a `name`, an `environ` in which `<root>` and `<home>` stand for a new temporary store root and HOME, and `calls`, each naming a writer function `fn`, its `args` and the `now` it runs at. metrics/fixtures/expected.json holds, for each case by name, every file the calls leave under the root with its exact bytes, and each call's return, with a warning cut after its subject. A copy conforms when running every case into a new temporary root produces exactly expected.json. node metrics/conform.ts metrics/fixtures/cases.json <output folder> runs the TypeScript writer over every case and prints the outcome as one JSON object to compare.

## Querying

The store is read with the DuckDB command-line tool. `read_json` with `format = 'newline_delimited'`, `union_by_name = true` and `hive_partitioning = true` reads every plugin's lines in one result, fills a field a plugin does not write with null, and adds `plugin`, `kind` and `repo` columns from the folder names. Set the session's time zone to UTC first, because DuckDB prints timestamps in local time otherwise.

```sql
SET TimeZone = 'UTC';
SELECT plugin, repo, run, usd
FROM read_json('~/.plugin-metrics/plugin=*/kind=summary/repo=*/*.json',
               format = 'newline_delimited', union_by_name = true, hive_partitioning = true)
ORDER BY ts DESC
LIMIT 10;
```

A glob that matches no file is an error in DuckDB, so a reader checks that a folder holds files before querying it. Spend over a run tree is summed by following `parent` from each child to its root with a recursive query, counting the runs that have no summary rather than treating them as zero.
