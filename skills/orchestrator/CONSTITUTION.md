# Orchestrator Constitution

Rules for the per-project president offices. The skill's SKILL.md is the operating
manual; this file is the invariants. All office-holders follow it.

The whole system is the skill folder plus per-machine state it derives
(`~/.claude/orchestrator/`). Copy the folder to another machine running Orca and it
works; each machine is its own island — own offices, own park-file, own ledger. Account
quota windows are shared across machines and race: who takes tokens first wins.

## Offices

- **President** — one per project. The single session that delegates work *for that
  project*; sole writer of its office comment. Project contexts must not mix: a president
  never dispatches into, reviews in, or triages another project's repos. Cross-project
  needs go president-to-president (a terminal message), never by reaching across.
- **The office plaque** is an Orca worktree comment on the project's main worktree:
  `OFFICE:president[<project>]=<session> since <UTC> | focus: <mission>`.
  One plaque per project; whoever is not named on a project's plaque delegates nothing
  there. Every transfer rewrites that plaque with a UTC timestamp and reason. History of
  government must be reconstructible from plaque rewrites plus terminal transcripts.

## Limits doctrine (why this design exists)

- Workers are **Claude only** (one account). Quota windows are **per account,
  machine-wide** — but presidents are per-project, so coordination happens through the
  **shared ledger on disk**, never through a super-president:
  - **Claude Code remaining is exact**: `scripts/limits.sh claude` runs
    `claude -p "/usage"` and parses the real server-side windows (session 5h, weekly
    all-models, weekly current-model) — a plain curl to the usage endpoint is
    Cloudflare-blocked, but the client passes it. It spins a short-lived `claude` process
    (~15-20s), so read it once per cycle, not per dispatch. Limits are per account, so the
    number covers every project's fleet at once. If the read fails, `claude_code.exact`
    is `false` and the value degrades to a transcript burn-rate estimate; a live CC
    terminal's `/usage` panel is the last-resort manual read.
  - **The park-file**: `~/.claude/orchestrator/parked-lanes.json`. Lanes are `claude`
    (whole account) and `opus` / `sonnet` (per-model weekly caps). A president that
    *observes* a limit-hit (a worker printing the limit message is ground truth) writes
    `{"<lane>": {"until": "<ISO reset>", "by": "<project>"}}` there so every other
    president sees the parked lane without probing. `limits.sh` folds it into its output
    and drops expired entries. Clear your own entry when the lane demonstrably works again.
- Two tiers, picked per dispatch by task difficulty (see SKILL.md's dispatch step):
  `opus` by default and for anything hard, `sonnet` for very simple mechanical work.
  Always the tier alias, never a pinned version — the CLI resolves it to the newest
  model. No Fable, no Codex.
- Routing rule of thumb: when the `opus` lane is constrained, shift work `sonnet` can do
  well onto it and queue the rest; never downgrade a judgment-heavy task to fit quota.

## Succession (pause and resume — no standing machinery)

1. **Pause before the wall.** The president reads its own burn on every dispatch cycle.
   With a single account there is no successor to hand over to: when the session or
   weekly window looks close to its cap, it stops delegating *immediately*, lets
   in-flight work reach a clean boundary, writes the `claude` lane into the park-file
   with the reset time, writes the 5-line brief to
   `~/.claude/orchestrator/briefs/<project>.md`, and rewrites the plaque to
   `paused until <reset UTC>`.
2. **The walled-president case is accepted, not engineered away.** If a president hits
   the wall without pausing, its session freezes visibly and nothing assumes office on
   its own. Recovery after the reset: start a session in the office worktree and take
   office — plaque + park-file + `worktree ps` + the Run inbox carry everything needed.
   No dead-man automation, no standing VP: dormant infrastructure rots faster than this
   failure mode occurs.
3. **Resumption.** Any session may take a paused office after the reset. It reads the
   brief (done / in-flight / changed / needs-decision / backlog head), rewrites the
   plaque, and deletes the brief once absorbed. Never two presidents of one project;
   the plaque decides.

## Delegation rules

- Dispatch goes through **Orca's orchestration layer** (Run → Task → `worker-start`;
  see SKILL.md) — one Task = one worktree = one agent. The task spec IS the task record —
  write it so a cold reader could review the result against it. The plain
  `worktree create --agent` path is the fallback for an Orca build without orchestration
  commands, not a parallel habit.
- The worker's repo CLAUDE.md defines its backlog source and definition of done; the
  president never overrides repo conventions from orbit.
- A test failure surfaced by a PR's own verification is part of that PR's definition of
  done: root-caused and fixed in the same PR, never filed away as a separate ticket.
- Every PR is reviewed by a fresh `opus` session in the worktree where it was built —
  never by the author's own terminal.
- Track progress via the coordinator inbox (`orchestration check --wait` for
  `worker_done`/`escalation`/`question`) and `worktree ps` — never by grep-watching
  worker screens (stale output false-fires) or polling workers with messages.
- Two agents must never hold the same task: check `orchestration task-list` and
  `worktree ps` for an existing task/worktree on that ticket before creating one (the
  RDRL-264/274 double-fix is the cautionary tale).
- Hot files discipline: work that touches a repo's most-contended files gets sequenced,
  not parallelized (the #326 stack-collapse lesson).

## Per-project adapter contract

The orchestrator core is project-blind. Per repo, it reads: backlog source + ticket
conventions, CI/DoD command, and branch rules **from that repo's CLAUDE.md**. A repo
without those in CLAUDE.md gets GitHub issues + "tests pass" as the fallback and a note
to fix its CLAUDE.md.
