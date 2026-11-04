# Hand-offs are checked at the producer against the program's owned formats

Status: accepted

Every file or value lighthouse hands to another plugin or reads from one has one owned format, a JSON Schema the harness program owns: lighthouse's verdict line (H13) and findings (H14), the pull request fields and render output (H15, H16), the interphase record (H11, which reaches acceptance lines K1 and locked checks K2) and check results (K3). lighthouse carries byte-identical copies of the program's validator and of these schemas, checks each hand-off immediately before writing or printing it and fails at that step naming the schema and every error, and reads each one only through its schema, refusing rather than defaulting, skipping or dropping. The child session's reply arrives as structured output under a reply schema narrowed from H13, and a reply or findings file that breaks its format is re-asked of the same session once with the errors before the run is blocked with them named. This was chosen because consumer-side patches lost data silently, such as a reviewer's findings discarded when a drive took the last JSON value of a prose reply; a fault is fixed where it is born.

## Considered options

- Keeping lighthouse's own partial validator: it ignored keywords the newer schemas use, so producer and consumer could disagree.
- Scanning the child's prose for its last verdict line: the failure that discarded findings in the pipeline.
- Refusing to compose a pull request without the pull-request plugin: breaks standalone use; lighthouse composes the same layout itself and checks it against H16 instead.

## Consequences

A schema change is a program decision, made in the program's copy and copied in unchanged. The pull request's prose is written by the child session as a fields draft, which lighthouse checks and the child fixes when refused.
