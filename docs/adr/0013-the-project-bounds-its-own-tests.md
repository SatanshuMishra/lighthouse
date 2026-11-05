# The project bounds its own tests

Status: accepted

Nothing in lighthouse or the pipeline puts a wall-clock limit on a project's test run, so a hung test is ended only by the project's own runner. lighthouse readiness therefore reads the profile's suite command, follows its package scripts and the script files they run, recognises each test runner, and decides from the project's own arguments and configuration files whether that runner ends a hung test; each runner that does not, or that readiness cannot recognise, becomes a test-bound readiness item the owner answers before an unattended run. Readiness reads these files and never runs the suite.

Considered options: lighthouse or the pipeline killing a test run at a limit, which is a cap the owner rejected; measuring the suite to find hung tests, which costs a full run and cannot prove a test never hangs; trusting every runner's default, which leaves node's test runner, unittest and cargo test unbounded with nothing said.

Consequences: a project whose runner has no per-test timeout, such as unittest, carries one readiness item until its owner answers it; an answer closes the item for good, even if the configuration later changes; a runner whose arguments are computed where the check cannot read them can be judged wrongly, and the item's question is how the owner corrects it.
