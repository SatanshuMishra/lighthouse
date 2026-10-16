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
