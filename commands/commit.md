# Commit — Stage everything and create a conventional commit

Stage all changes and commit with a well-formed conventional commit message. Never push — the user always pushes manually.

## Steps

1. Run `git status` (no `-uall`) and `git diff` to understand what is being committed.
2. Run `git diff --cached` to see anything already staged.
3. Derive the commit type from the changes:
   - `feat` — new feature or capability
   - `fix` — bug fix
   - `docs` — documentation only (README, CLAUDE.md, comments)
   - `refactor` — restructuring without behavior change
   - `test` — adding or updating tests
   - `chore` — tooling, deps, config, build system
   - `perf` — performance improvement
4. Write a concise subject line: `<type>(<optional scope>): <what changed>` — under 72 chars.
5. If the change warrants it, add a short body (1–3 lines max) explaining WHY, not WHAT.
6. Run `git add .` to stage everything.
7. Commit using a HEREDOC to preserve formatting. Do not add a `Co-Authored-By` trailer — the commit is authored by the user (via their `git config user.name`/`user.email`), not Claude.

## Rules

- **Never push.** The user always pushes themselves.
- Never use `--no-verify` or skip hooks.
- Never amend an existing commit — always create a new one.
- Do not commit files that look like secrets (`.env`, credential files). Warn the user if any are staged.
