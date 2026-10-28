# Acceptance lines are run by code and judged only from check results

Status: accepted

When a FEATURE branch comes with an interphase record, lighthouse execute runs each acceptance line's command itself from the FEATURE worktree and writes one check result per run, in the K1 and K3 shapes of the harness-redesign contracts, and lighthouse verdict judges those lines only from the check results, demanding existing evidence and every required run, and counting a record line with no check result as unproven; the findings file keeps neighbours and record-less runs. The model sat between the check and the verdict before, and a skipped retry, a partial trial pass or a missing evidence file turned real failures green; writing neighbour and model-planned paths as check results too was rejected because the frozen K3 shape admits only criterion ids.
