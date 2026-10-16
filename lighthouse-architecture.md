# lighthouse-architecture: Design lighthouse: verify a merged feature branch before it reaches production
Status: active
Updated: 2026-10-16T06:59:38.390Z
Next ids: c8 D17 R15 S8

## Goal

Design lighthouse, a config-agnostic Claude Code plugin that proves a merged feature branch broke nothing before it opens the pull request into production, and keep investigating and improving that architecture until the human says it is ready to build. It is the step after interphase (spec) and mitosis (parallel build) in the human's pipeline, but it depends on neither and must work for anyone.

## Done when

- [ ] c1 The human states, in their own words, that the lighthouse architecture is ready to build
- [ ] c2 The default number of trials and the error-bar thresholds for output that varies are decided
- [ ] c3 The contents of an observation record are decided
- [ ] c4 The time and money budget per run, and what to skip when over it, are decided
- [ ] c5 The flow after lighthouse reports, recommends and stops on a behaviour difference is decided
- [ ] c6 How the PR's What changed field is filled is decided (proposed so far: commit subjects since production, up to 8 lines)
- [ ] c7 Section 15 of docs/architecture/lighthouse-architecture.html has no row marked Open or Proposed

## Where things stand

Converted from the old ledger.

## Next step

In a fresh session in this repository, read docs/architecture/lighthouse-architecture.html and docs/research/2026-09-28-verification-research.md, then wait for the human's specific questions or instructions about the architecture. Do not start building. Put criteria c1 and c7 to the human to settle, and take up the undecided items (c2 to c6) only when the human chooses to.

## Decisions in force

- D1 Lighthouse is a separate plugin whose one job is to prove the merged whole broke nothing: A separate plugin. interphase decides what to build, mitosis builds it in pieces, lighthouse proves the merged whole broke nothing before the PR into production. It never merges or deploys; a person does.
- D2 Lighthouse is independent and config-agnostic: its only inputs are git and the project's own harness: Its inputs are two branch names (the merged feature branch and production) and the harness in the project's repo. It never reads a spec, a Steps file or a PR list, and never depends on the user's ~/.claude configuration, skills or MCP servers. Every external action is a command the project records in its harness.
- D3 Lighthouse never writes tests about features and never works out intent: Lighthouse only runs checks whose right answer it never has to work out. Right answers come from the project's existing tests and rules, from production's behaviour on the same input, or from universal failure signals (crash, hang, server error, console error, failed start). Proving new features correct belongs upstream. A green verdict means the merge broke nothing lighthouse could see, not that features are right.
- D4 Testing is live and built from generic probes: inputs from the product, no expected answers: A probe is one input, run against one build, recorded as one observation, with four parts: input source, driver, observation, judge. It is generic when its input comes from the product itself (pages, API description, commands, recorded sessions, task list) and its verdict needs no knowledge of intent. Lighthouse may generate inputs but never decides what the right answer is.
- D5 One harness for any software, organised by how a product is controlled and observed: Seven ways in: screen, message, process, library call, stored state, device, task in a sandbox. Any of them can have output that varies run to run, which changes the judge, not the driver. For anything else the project supplies one driver command: it gets one input and one build, runs it, prints one observation record, exits 0 if it ran and anything else if it could not, and never decides pass or fail.
- D6 The baseline is production, re-run live every time, never stored snapshots: Every run builds production twice and the merged branch once, each in a throwaway environment. Differences between the two production copies are noise and are filtered from the comparison. Production results are cached locally by production commit.
- D7 Gate on not worse only; capability scores are history, never a pass bar: Lighthouse blocks only on getting worse. Every run's scores go into a local history, which is the benchmark over time, and never decide a release.
- D8 Three judges, and lab practice for output that varies: Universal judge: things always wrong, new occurrences block. Declared judge: the project's tests, schemas, invariants and graders, a newly broken rule blocks. Production judge: differences beyond noise are reported. For varying output: fresh sandbox per trial, several trials, paired comparison with production, error bars, pass^k for works-every-time, pinned and recorded settings, a known-good solution per task, program graders decide and model graders only advise. Newly failing checks are re-run before any verdict to rule out flakiness.
- D9 Every project must be initialised; declining means lighthouse is not used; initialize --force starts fresh: The first ship request in a project with no harness offers to initialise; if declined, lighthouse is not used there. Initialise detects what the repo says, then asks the rest in rounds, then runs a proof run: build and start everything, run every existing check on production, make each kind of check fail once on purpose, measure noise, time and cost. Answers a person gives are tested in that proof run. An interrupted initialise writes nothing to the repo. initialize --force builds a new harness from scratch and replaces the old one only when the new proof run passes; results are untouched. Initialise may write drivers and environment recipes (they hold no expected answers) but never rules or graders; the human did not contest this.
- D10 The harness is tracked in git; results stay local and outside the repo: Harness, tracked in one folder in the repo: config (branches, ways in, trials, thresholds, budget, PR command), environment recipes, drivers, discovery starting points, the store of inputs, and the fact list with a way to re-check each fact. Results, never tracked, kept in a per-project folder under the home directory outside the repo (as mitosis keeps ~/.mitosis/runs, mitosis.py:67): observation records, evidence, verdicts and full reports, measures, cached production results, history. Every result is stamped with the harness version and both commits. Results never rewrite the harness except by promoting an input that caught a regression, never its figures. Secrets are referenced by name only.
- D11 Every run checks and repairs the harness; shipping never needs a re-initialise: Each fact in the harness is stored with a way to re-check it. At the start of every run each fact is re-checked against both branches and new facts are looked for. Still true: nothing. Changed and derivable: updated automatically with a proof for that part only. Changed and only a person knows: just that one question. Gone: removed and listed for review. The check may add and repair but never removes or weakens a check to make a run pass.
- D12 Harness changes from a run land as their own commit on the feature branch: Their own commit on the feature branch, so they travel in the production PR for review.
- D13 PRs open only through the project's established PR tool, and the verdict fills its fields: The harness records the project's PR tool at initialise and lighthouse never opens a PR another way. For pr.mjs: title from a harness template that passes the title rule; Verified lines only for checks that ran and passed; Not verified for unchecked surfaces, code nothing ran and flaky checks; Risk for the review items; no links because results are local. The PR carries a summary and the full report stays local. What changed is still proposed as commit subjects since production, up to 8 lines.
- D14 Behaviour differences: report, recommend and stop; never block: Lighthouse reports each behaviour difference with a recommendation and stops for a person; a difference never blocks on its own. Still open: what happens after the person answers (continue to the production PR in the same run, or end so the next ship request starts a new run).
- D15 Private tasks are dropped unless they prove useful: Dropped by default. Reintroduce them only if evidence shows builders tuning to visible tasks.
- D16 The plugin is named lighthouse, in a private Apache-2.0 repository: lighthouse, at https://github.com/SatanshuMishra/lighthouse, private, Apache-2.0, cloned to /Users/satanshumishra/Documents/DevLabs/lighthouse.

## Open risks

- R1 Automatic exploration has a ceiling: on 52 real Android bugs, 18 were found by none of six exploring tools, because long paths and specific text inputs stopped them. A run that finds nothing is not proof nothing broke; the project's sign-in route and key flows still matter.
- R2 Record-and-replay is not fully reliable: tools failed to replay 17% of scenarios and 44% of crashing bugs reliably, and 45% of flaky UI tests came from waiting on loading content. Every replay needs built-in waits and the flakiness check.
- R3 Live testing has side effects: clicking around creates accounts, sends email and charges cards. Every build must run in a throwaway environment on test data, never against live data or production systems.
- R4 Rules and graders do not write themselves. Without the project's own invariants and eval graders, lighthouse's checks stop at universal failure signals and comparison with production, so its verdict covers less.
- R5 Output that varies costs many runs: detecting a 3-point change took about 969 questions in one worked example, so small task sets only catch large regressions. No source gives a threshold for the number of trials or for pass^k.
- R6 Shared test infrastructure usually fails on environments, ownership and flaky tests rather than on its core (Google's large-test experience). Environment building and flakiness handling need to be built first and hardest.
- R7 Some platforms are weak: the main Windows desktop driver (WinAppDriver) has had no stable release since November 2020, and iOS testing needs a Mac. Expect more unchecked surfaces there.
- R8 A green verdict can be misread as the features being correct. It only means the merge broke nothing lighthouse could see. In pipelines without upstream feature tests, that gap is large; the report must list changed code that nothing ran.
- R9 Results live on one machine: history and benchmarks are lost if that folder is wiped, and timings and costs do not compare across machines.
- R10 The harness is only re-checked when a run starts, so a fact that changes between runs (for example a disabled test account) surfaces only at the next ship request, as a question at that point.
- R11 Lighthouse commits its own harness changes to the feature branch. A harness change that removes or weakens a check could turn a failing run green; the rule forbids it and requires removals to be listed, but nothing enforces the rule yet.
- R12 claude plugin eval compares with-plugin against without-plugin only; no documented mode compares two versions of a plugin. Running it once per branch and diffing the JSON output is an unverified workaround.
- R13 The pr skill points to ~/.claude/rules/common/git/pull-requests.md, which does not exist on this machine as of 2026-09-28; the PR field rules were read from pr-format.mjs instead. A separate task was offered to restore that file.
- R14 Report, recommend and stop is decided, but the flow after the person answers is not. Until it is, a behaviour difference could leave a run stopped with no defined way to continue to the production PR.

## Settled, do not reopen

- S1 Out of scope: Writing tests, rules or graders about what new features should do, or working out intent from specs or code; that belongs upstream.
- S2 Out of scope: Fixing anything lighthouse finds; failures go back to whoever builds.
- S3 Out of scope: Merging into production or deploying; a person does that.
- S4 Out of scope: Touching live data or production systems during a run.
- S5 Out of scope: Using capability or benchmark scores as a gate; they are history only.
- S6 Out of scope: Private tasks kept outside the repo, unless evidence shows they are needed.
- S7 Out of scope: Tracking results in git: reports, records, screenshots, benchmarks and history stay local.

## Where the details live

- Architecture report (HTML, 16 sections, the design as agreed so far): docs/architecture/lighthouse-architecture.html
- Verification research digest with sources and known gaps: docs/research/2026-09-28-verification-research.md
- Original report before the rename from shipping to lighthouse: /Users/satanshumishra/.agent/diagrams/shipping-architecture.html
- GitHub repository (private, Apache-2.0): https://github.com/SatanshuMishra/lighthouse
- PR tool field rules and caps, read from code: /Users/satanshumishra/.claude/lib/git/pr-format.mjs
- Upstream context: mitosis gate that tests each MSP alone: /Users/satanshumishra/Documents/DevLabs/mitosis/run.py
- Old ledger record: thread 01M3N8HQ86N92W3MWXMB6RQ8E7 in refs/logbook/archive/ledger
