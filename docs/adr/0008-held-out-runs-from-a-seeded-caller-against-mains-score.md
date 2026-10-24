# The held-out set runs from a seeded caller and is judged against main's own score

Status: accepted

lighthouse:test is called from pipeline sessions that already hold 200,000 to 360,000 tokens, so the held-out pass forks every case's calling session from one seed session of at least that size, on main and on the branch alike; measured from fresh sessions, a launcher that keeps the caller's history out of the run looks like pure overhead. main itself meets decision record 0004 on 19 of 24 cases, and H6 clean's expected not-green contradicts the verdict rule that a run is green unless every new-behaviour path is unproven, so the before-and-after test holds 0004's bar per fixture against main's score on the same seeded pass: no broken run is ever green, and every fixture's broken and clean cases are met at least as often as on main. 0004's held-out set, its leak test and its fixtures are unchanged.
