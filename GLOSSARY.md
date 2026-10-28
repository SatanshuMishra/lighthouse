# lighthouse

lighthouse proves a FEATURE branch of any kind of software works before it merges into its core branch: the project's own suite, the product as a person or calling program uses it, and the surfaces next to the change.

## Language

**Core branch**:
The long-lived branch a repository ships from, such as main, master or development.
_Avoid_: base branch, trunk

**FEATURE branch**:
The branch holding every merged change under test, which one pull request carries into the core branch.

**Profile**:
The committed description of how to build, start, reach, sign into and test one project, at .lighthouse/profile.json.
_Avoid_: config, ruleset

**Surface**:
One way a person or calling program uses the product, such as a command, a page or flow, an endpoint group, a public module, a skill or a device feature, with the code paths behind it.

**Fact**:
One thing the profile records that may need confirming, with whether it is confirmed and how to re-check it.

**Product path**:
One thing to try on a build, judged against an expected outcome.
_Avoid_: scenario, test case

**New-behaviour path**:
A product path for something the change adds, judged against the change's intent.

**Neighbour**:
A surface whose code paths include a changed file or a file that uses something the change altered, one hop away.
_Avoid_: blast radius, impacted area

**Verdict**:
The computed outcome of one run: green, failures, blocked or unproven.

**Unproven**:
Not reached, so neither passed nor failed; never counted as passed.

**Flaky**:
Failed once and passed on retry, or passed some but not every trial.

**Results folder**:
The folder one run writes its worktrees, evidence, findings and report into.

**State folder**:
lighthouse's per-repository folder outside the repository, ~/.lighthouse/<repository folder>, holding the credentials file and stored answers.

**Held-out set**:
Fixture projects with planted integration bugs that lighthouse is judged on and never tuned on.

**Retired fixture**:
A held-out fixture whose planted bug a skill author was shown, so it no longer counts as held out and is replaced.

**Probe**:
A script kept beside a held-out fixture's folders, never committed into its builds, that fails on the broken FEATURE and passes on the clean twin, proving the planted bug is real.

**Previous results**:
The results folder of an earlier lighthouse:test run on the same FEATURE branch, holding its findings and the core and FEATURE commits it tested.

**Carried path**:
A product path that passed in the previous results on a surface no new commit touched, whose result and evidence are copied forward instead of driven again.


**Child session**:
The separate headless Claude Code session in which lighthouse:test does its work, started by the launcher from the results folder with a fresh context, so the caller's history is never re-read.

**Driver agent**:
lighthouse's own subagent, lighthouse:driver, through which the child session drives every product path, with a one-hour prompt cache so a long hold for a build or a VM does not rewrite its context.

**Check**:
How a product path's expected outcome is observed: suite (named project tests that passed), direct (a call whose response holds the outcome) or drive (the surface's recorded driver), recorded with why it fits; the lightest one that still observes the outcome is used.

**Mark**:
A timed start or end line a session writes with lighthouse mark around a step, build or path, so its minutes and tokens can be attributed to it.

**Metrics store**:
The folder tree shared by the pipeline and its plugins, ~/.plugin-metrics or PLUGIN_METRICS_DIR, where lighthouse launch records every lighthouse:test run as two events and one run summary.
_Avoid_: ledger, runs.jsonl

**Acceptance line**:
One criterion's runnable check in an interphase record, with an id such as C2.1, a surface, a command run from the repository root and what passing means; lighthouse runs it as a check named by that id.
_Avoid_: acceptance test, criterion check

**Check result**:
One run of an acceptance line as lighthouse execute recorded it: its id, the FEATURE commit, pass, fail or could-not-run, its evidence, its seconds and its runner; the verdict judges acceptance lines only from these.

**Could-not-run**:
A check result or measurement that neither passed nor failed because the check could not decide, such as a command that hit its limit or a pixel sample too close to a threshold; it makes its check unproven, never failed.

**Reach command**:
A surface's command that exits 0 when this machine can drive that surface with its recorded driver; its exit sets the surface's available.

**Measured durations**:
The seconds lighthouse profile measure recorded in the profile for setup, build, the suite, the start command until ready and each reach command, from which every time limit is derived.

**Run summary**:
The one line per lighthouse:test run in the metrics store holding its verdict, suite, product paths and own spend, replaced whole when written again.

**Parent run**:
The run that started a lighthouse:test run, named as <plugin>/<run id>, such as the pipeline run whose Integration called it; empty when lighthouse runs alone.

**Own spend**:
What one lighthouse:test run cost: every message of its child session, driver agents and trial sessions, and of the caller's own turns between its start and end, counted once and priced when the run summary is written.

**Expired rewrite**:
A model turn that writes its whole context to the prompt cache again because the gap since its previous turn outlived the cache.

**Seed session**:
The claude -p session a held-out pass starts once with a fixed history of at least 200,000 tokens, which every case's calling session forks, so lighthouse:test is measured as a pipeline session calls it; its own spend is reported apart and counted in neither total.
