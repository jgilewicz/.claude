# CLAUDE.md — Global Instructions

Stack: **Python 3.13 only** (Bash allowed for scripts/automation). Nothing else.

---

## 1. Philosophy

- **No speculative features** — no flags, options, or config until actually needed.
- **No premature abstraction** — extract a utility only after writing the same code three times.
- **Clarity over cleverness** — explicit and readable beats dense one-liners.
- **Justify new dependencies** — each one is attack surface and maintenance burden.
- **No phantom features** — never document or validate what isn't implemented.
- **Replace, don't deprecate** — delete the old implementation. No shims, dual config formats, or migration paths. Flag dead code proactively.
- **Verify at every level** — linters, type checker, hooks and tests go in first, not last. Prefer structure-aware tools (`ast-grep`, LSP, compilers) over text matching.
- **Bias toward action** — decide and move on anything easily reversed; state the assumption out loud. Ask first before locking in interfaces, data models, architecture, or destructive/write operations on external services.
- **Finish the job** — handle visible edge cases, clean up what you touched, flag adjacent breakage. Thoroughness, not gold-plating.
- **Agent-native by default** — agents should reach any outcome a user can. Tools are atomic primitives; features are outcomes described in prompts. Prefer file-based state.

---

## 2. Comments

Code is self-documenting. If a comment explains **what** the code does, refactor the code instead.

- Single `#` only when the **why** is non-obvious: hidden constraint, subtle invariant, workaround.
- No comment blocks, no docstring padding, no commented-out code — delete it.

```python
# BAD
# increment the counter by one
counter += 1

# GOOD
# retry once: upstream returns 502 on cold start
response = _fetch(url) or _fetch(url)
```

---

## 3. Python style

- Preserve existing formatting, line length, and naming in the file being edited.
- **Always annotate types**, even when awkward — use `Any`, `TypeVar`, `Protocol`.
- `ruff check --fix` + `ruff format` run automatically on every edit.

```python
from typing import Protocol

class Sampler(Protocol):
    def sample(self, n: int) -> list[float]: ...

def summarize(sampler: Sampler, n: int = 10) -> dict[str, float]:
    xs = sampler.sample(n)
    return {"mean": sum(xs) / len(xs), "max": max(xs)}
```

### Hard limits

1. ≤100 lines per function, cyclomatic complexity ≤8
2. ≤5 positional parameters
3. 80-char line length
4. Absolute imports only — no `..` relative paths

```python
# BAD
from ..losses.ppo import clipped_surrogate

# GOOD
from ppo_dr.losses.ppo import clipped_surrogate
```

### Zero warnings

Fix every warning from every tool. If one genuinely can't be fixed, add an inline ignore **with a justification**. Clean output is the baseline, not the goal.

### Error handling

- Fail fast with actionable messages.
- Never swallow exceptions silently.
- Include context: what operation, what input, suggested fix.

```python
# BAD
try:
    cfg = json.loads(path.read_text())
except Exception:
    cfg = {}

# GOOD
try:
    cfg = json.loads(path.read_text())
except json.JSONDecodeError as e:
    raise ValueError(
        f"invalid JSON in {path} at line {e.lineno}: {e.msg}. "
        "run `just validate-config` to check the schema"
    ) from e
```

---

## 4. Architecture

| Framework style | Rule |
|---|---|
| PyTorch / OOP | Modular, class-based. One responsibility per class. |
| JAX / functional | No classes for logic. Organize by function role into subfolders (`losses/`, `networks/`, `utils/`). Models via equinox/flax are fine. |

### Project structure (every new project)

```
<project_name>/          # uv-inited root
  <module_folder>/       # main codebase (e.g. ppo_dr/ for ppo_dr_jax)
  tests/                 # mirrors module structure
  justfile
  README.md
  CLAUDE.md
  pyproject.toml
```

---

## 5. Tooling

**Runtime:** Python 3.13 with `uv venv`.

| purpose | tool | never use |
|---|---|---|
| deps & venv | `uv` | pip, poetry |
| lint & format | `ruff check` · `ruff format` | black, pylint, flake8 |
| static types | `ty check` | mypy, pyright |
| tests | `pytest -q` | — |

Configure strictness via `[tool.ty.rules]` in `pyproject.toml`. Build backend: `uv_build` for pure Python, `hatchling` for extensions.

**Supply chain:** `pip-audit` before deploying · pin exact versions (`==`, not `>=`) · `uv pip install --require-hashes`.

**Versions:** when adding dependencies, CI actions, or tool versions — look up the current stable release. Never assume from memory unless the user supplies one.

### CLI tools

| tool | replaces | usage |
|---|---|---|
| `rg` | grep | `rg "pattern"` — literal strings, log messages |
| `ast-grep` | — | `ast-grep --pattern '$FUNC($$$)' --lang py` — code structure |
| `fd` | find | `fd -e py` |
| `shellcheck` | — | `shellcheck script.sh` |
| `shfmt` | — | `shfmt -i 2 -w script.sh` |
| `zizmor` | — | `zizmor .github/workflows/` |
| `wt` | git worktree | `wt switch branch` |
| `trash` | rm | `trash file` — **never `rm -rf`** |

Searching for calls, class definitions, imports, or argument patterns → `ast-grep`. Searching for a string → `rg`.

---

## 6. Bash

- Always `shellcheck` + `shfmt -i 2 -w`.
- `set -euo pipefail` at the top of every script.
- Quote every expansion: `"$var"`, `"${arr[@]}"`.
- Bash is for glue only. Once a script needs data structures or branching depth, rewrite it in Python.

```bash
#!/usr/bin/env bash
set -euo pipefail

target="${1:?usage: sync.sh <target>}"
rsync -a --delete "./build/" "$target"
```

---

## 7. Testing

Tests live in `tests/`, mirroring package structure.

- **Test behavior, not implementation.** If a refactor breaks the tests but not the code, the tests were wrong.
- **Test edges and errors, not just the happy path.** Empty inputs, boundaries, malformed data, missing files, network failures. Every handled error path gets a test that triggers it.
- **Mock boundaries, not logic.** Only mock what is slow (network, filesystem), non-deterministic (time, randomness), or an external service you don't control.

```python
# BAD - asserts internals
def test_cache():
    c = Cache()
    c.get("a")
    assert c._store_hits == 1

# GOOD - asserts behavior, covers the edge
def test_cache_returns_stored_value():
    c = Cache()
    c.set("a", 1)
    assert c.get("a") == 1

def test_cache_raises_on_missing_key():
    with pytest.raises(KeyError, match="a"):
        Cache().get("a")
```

---

## 8. Workflow

**Before committing**

1. Re-read the diff for unnecessary complexity, redundancy, unclear naming.
2. Run the relevant tests — not the full suite.
3. Run `ruff check`, `ruff format`, `ty check` — fix everything.

**Commits**

- Imperative mood, ≤72-char subject, one logical change per commit.
- Never amend/rebase commits already pushed to shared branches.
- Never push directly to `main` — feature branches and PRs.
- Never commit secrets — `.env` (gitignored) plus environment variables.

**Hooks and worktrees**

- `prek install` in every repo · `prek run` before committing · `prek auto-update --cooldown-days 7`.
- Parallel subagents require worktrees: each subagent works in its own (`wt switch <branch>`), never the main repo, never a shared working directory.

**Pull requests**
Describe what the code does now — not discarded approaches or prior iterations. Only what's in the diff. Plain, factual language: a bug fix is a bug fix. Avoid *critical, crucial, essential, significant, comprehensive, robust, elegant*.

**Code review**
Order: architecture → code quality → tests → performance. `git fetch origin` first. Per issue: concrete `file:line` reference, options with tradeoffs when the fix isn't obvious, one recommendation, then ask before proceeding.

---

## 9. Documentation

After every major codebase change, update `README.md` **and** `CLAUDE.md`. Bullet points, no walls of text.


## 10. Speaking Style
- Be concise, no fluff
- Use bullet points instead of text blocks
- Keywords/phrases over full sentences where possible
- No intros, summaries, or repetition
- If the answer fits in one sentence, make it one sentence
- Priority: information > form
- Avoid outputs >20-30 lines unless explicitly asked for detail
- No explaining "why I did this" unless asked
- Don't repeat the user's question back
