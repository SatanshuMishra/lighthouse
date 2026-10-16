# The command computes the verdict; the skill only reports findings

lighthouse is split into a standard-library Python command for every step with one right answer and three skills for the judgement of understanding, driving and judging a product. The lighthouse:test skill writes what it found to findings.json, and lighthouse verdict computes green, failures, blocked or unproven from it, so the agent can never talk itself into green. Putting the whole flow in skill prose was rejected because a false green is the failure that matters most.
