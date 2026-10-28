# Hung work ends at a time limit derived from measured durations

Status: accepted

lighthouse profile measure runs a project's setup, build, suite, start command and reach commands once and records their seconds in the profile, and one function derives every time limit from them: the suite and each check at three times the measured suite time with a floor of 60 seconds, the child session at twice that plus six times the measured setup, build, start and driver seconds plus a fixed three-hour allowance for the model's work, and the run ten minutes beyond the child. A step that reaches its limit ends blocked or could-not-run with the limit named, never failed, and scope is still never narrowed. This supersedes ADR 0007 for time only: no caps let one hung child, suite or wait stall a pipeline for a day, while fixed caps with no measurement would cut a legitimately long suite.
