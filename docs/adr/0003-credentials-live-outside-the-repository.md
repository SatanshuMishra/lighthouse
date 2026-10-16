# Test credentials live outside the repository and never reach the model

Credential values live only in ~/.lighthouse/<repository folder>/credentials.env, readable by the owner alone, or in the project's own gitignored file. The profile records names, never values; only the lighthouse command reads values and puts them into a child process, redacting them from its output, and production-marked entries are refused. A gitignored file inside the repository was rejected because a worktree, a copy or a mistaken commit can carry it along.
