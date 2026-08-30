# Complete — Update README.md and CLAUDE.md from unstaged changes

Inspect the current working tree and update project documentation to reflect any changes not yet staged for commit.

## Steps

1. Run `git status` to identify modified, new, or deleted files (do NOT use `-uall`).
2. Run `git diff` to see unstaged changes to tracked files.
3. For new untracked files, read them to understand what they add.
4. Synthesize what changed: new modules, removed code, renamed files, config changes, dependency updates, architecture shifts.
5. Update **README.md** — keep it concise (bullet points). Reflect the current state of the project, not the delta.
6. Update **CLAUDE.md** — same principle. Focus on facts a future Claude session needs: structure, conventions, important modules, env setup. No walls of text.

## Rules

- Do NOT stage or commit anything.
- Do NOT create new files other than README.md / CLAUDE.md if they are missing.
- Strip explanatory or descriptive comments from code you touch — but here you are only editing docs, not code.
- Keep both files concise. Remove stale information. Bullet points preferred over prose.
