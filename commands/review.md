# Review — Bug audit (latest Opus) → Fix implementation (latest Sonnet)

Two-phase pipeline: the latest Opus model audits the codebase strictly for bugs at high effort, then the latest Sonnet model implements every approved fix.

Use `model: "opus"` for the audit agent and `model: "sonnet"` for fixes — these always resolve to the newest available model of each family.

---

## Phase 1 — Prepare context

Before spawning the audit agent:
1. Read `README.md` and `CLAUDE.md` (if they exist) for project overview and conventions.
2. Run `find . -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" \) | grep -v __pycache__ | grep -v node_modules | grep -v .venv | grep -v dist` to enumerate source files.

---

## Phase 2 — Bug audit (spawn Agent with model="opus")

**Prompt to pass:**
```
You are a senior engineer doing a high-effort bug audit. Your ONLY job is to find real bugs — not style issues, not "could be cleaner" notes, not missing docs. Only report things that are wrong in a way that would cause incorrect behavior, crashes, data loss, race conditions, off-by-one errors, incorrect logic, broken edge cases, misused APIs, or silent failures.

Project overview (README.md):
<readme>
{README content or "not present"}
</readme>

Project conventions (CLAUDE.md):
<claude_md>
{CLAUDE.md content or "not present"}
</claude_md>

Source files to audit:
{List all files, then read and analyze each one.}

For each bug found, output:

**[BUG-N] Short title**
- File: `path/to/file.py`, line ~N
- What is wrong: one sentence
- Why it matters: one sentence (crash / wrong output / data corruption / etc.)
- Fix direction: one sentence — concept only, no code

Do not mention clean files. End with a summary table:
| # | File | One-line description | Severity (high/med/low) |
```

---

## Phase 3 — Report + user approval

Present the Opus agent's findings verbatim. Keep it concise.

Ask: **"Implement all fixes, or specific ones? (reply 'all' or list e.g. BUG-1, BUG-3)"**

Wait for the user's reply before proceeding.

---

## Phase 4 — Fix implementation (latest Sonnet, i.e. you)

For each approved bug:
1. Re-read the relevant file(s).
2. Apply the minimal correct fix — do not refactor surrounding code, do not add comments, do not touch unrelated logic.
3. After all fixes, run available lint/test commands (`ruff check --fix` + `ruff format` for Python if applicable).
4. Report what changed: file + line + one sentence per fix.

Do not stage or commit unless the user asks.
