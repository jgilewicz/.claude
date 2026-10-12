---
name: orchestrator
description: Assume the president role for THIS project — delegate work to Claude worker sessions (Opus/Sonnet, newest of each) in their own Orca worktrees, routed by real Claude Code usage limits and a shared park-file. When the account window nears its cap, pause cleanly and resume after reset. Use when the user says "orchestrate", "become orchestrator", "delegate this backlog", "president", asks who holds the office, or wants work fanned out across agents by remaining quota.
---

# Orchestrator

Offices are **per project**; project contexts never mix. Invariants live in
[CONSTITUTION.md](CONSTITUTION.md). Read the constitution once per term. The whole
system is this folder plus `~/.claude/orchestrator/` (derived per machine) — portable by
plain copy; machines are independent islands racing on shared account quota.

Workers are **Claude only**, in two tiers: `opus` and `sonnet`. Never Codex, never Fable.

## Take office (for the project you are in)

1. `orca worktree ps --json` → find the comment starting `OFFICE:president[<this project>]`.
   Other projects' plaques are not your business — never touch them. If another live
   session holds this project's office, ask the user before contesting; if it's you or
   vacant:
2. If `~/.claude/orchestrator/briefs/<project>.md` exists, a previous term paused at the
   quota wall — read it and continue from it.
3. `orca worktree set --worktree <this project's main worktree> --comment
   "OFFICE:president[<project>]=<your session name> since <UTC> | focus: <current mission>"`
4. Ensure `~/.claude/orchestrator/parked-lanes.json` exists (`mkdir -p` + `echo '{}'` if
   missing) — it is the cross-office ledger of rate-parked lanes.
5. **Bind the term's Run**: `orca skills get orchestration` (read the version-matched
   guide once per term — flags drift between Orca releases), then
   `orca orchestration run-create --objective "<project> presidency: <mission>" --json`,
   or reuse the term's existing Run from `run-list`. Append `| run: <run_id>` to the
   plaque so a resuming president finds the inbox.

## Each dispatch cycle

1. **Limits**: `~/.claude/skills/orchestrator/scripts/limits.sh all` — route by the
   constitution's doctrine. Run this before *every* dispatch of any kind (implementation,
   review, rebase — no exceptions): a fresh snapshot, not the one from the last cycle.
   The output includes `parked` lanes from the shared park-file — another project's
   president may have parked a lane you can't see from your own workers. A worker that
   just printed a limit-hit message parks that lane until its reset: **write the
   park-file entry** (`{"<lane>": {"until": "<ISO reset>", "by": "<project>"}}`, lane =
   `claude` for the whole account, `opus` / `sonnet` for a per-model weekly cap) so other
   presidents see it. If the session or weekly all-models window looks near its cap, stop
   delegating and pause (see "Quota wall"). Remaining comes exact from `claude -p
   "/usage"` (spun by limits.sh, ~15-20s). If that read fails, `claude_code.exact` comes
   back `false` and the value is a burn-rate estimate; only then fall back to reading a
   live CC terminal's `/usage` panel.
2. **Backlog**: from this repo's CLAUDE.md-declared source (Jira/GH issues).
3. **Dedupe**: check `worktree ps` — never two worktrees for one ticket.
4. **Delegate — via the orchestration layer (primary)**:
   ```
   orca orchestration task-create --spec "<self-contained brief: ticket, repo conventions pointer, DoD>" --json
   orca orchestration worker-start --task <task_id> --worktree new-top-level --name <ticket-slug> --agent claude --model <opus|sonnet> --setup run --json
   ```
   The task spec IS the task record — write it so a cold reader could review the result
   against it. `--model` sets the tier at launch (no `/model` dance); read the receipt's
   `launch.effective` to verify. Create every independent Task first and start all their
   workers before waiting.
   *Fallback (older Orca without orchestration commands, or a quick untracked one-off):*
   `orca worktree create --name <ticket-slug> --no-parent --agent claude --prompt "<brief>"`
   — then track by `worktree ps` and set the model by sending `/model <opus|sonnet>`
   after boot.
   A test failure surfaced by the PR's own verification (CI, integration suites) is part
   of that PR's definition of done: it gets root-caused and fixed **in the same PR**,
   never filed away as a separate ticket — even if it looks pre-existing on main.
   **Model tiering** — assess each task's difficulty before dispatch and pick the
   cheapest tier that can do it well:
   - **`opus`**: the default — ordinary implementation (ticket → tests → PR) and anything
     hard: cross-cutting architecture, ambiguous specs, gnarly debugging.
   - **`sonnet`**: very simple mechanical tasks — renames, changelog entries, doc fixes,
     small config tweaks, one-file patches with an obvious shape.
   Always pass the tier alias, never a pinned versioned id — the Claude CLI resolves it to
   the newest model of that tier.
5. **Harvest — via the coordinator inbox (primary)**:
   `orca orchestration check --wait --types worker_done,escalation,question --timeout-ms 900000 --json`
   — never grep-watch worker screens for completion (screen-scraping false-fires on stale
   output). Process the whole Delivery: `reply` to `question` messages, inspect results
   with `worker-show`/`worker-read --dispatch <id>`, then `worker-release` each settled
   dispatch (or `worker-start --task <next> --terminal <handle>` to reuse the agent)
   before `check --ack`. Update the plaque's `focus:` at meaningful checkpoints.
   *Fallback:* `worktree ps` for state/linkedPR + reading finished workers' terminals.
6. **Review dispatch**: review a PR **in the worktree where it was implemented** — a
   review Task started there: `worker-start --task <review_task> --worktree <exact
   existing worktree> --agent claude --model opus` (creates a fresh agent terminal in
   place, no setup rerun; fallback: `orca terminal create --worktree path:<wt> --command
   "claude --model opus"`). The reviewer is always a **fresh session**, never the author's
   terminal. Never a second worktree for the same task. Only when no local workspace
   holds the branch (e.g. it was built in a since-repurposed worktree) create a dedicated
   review worktree on the PR branch. Reviewer tier is `opus`; only when the `opus` lane is
   parked, review trivial `sonnet`-tier changes with `sonnet` and hold the rest until the
   reset.

## Cross-project business

Never dispatch into another project's repos. If your backlog names work that lives in
another project (a cross-repo ticket), message that project's president
(`orca terminal send` to the session named on its plaque) — or, if that project has no
president, tell the user and let them decide whether to seat one.

## Quota wall (do not skip when the account window nears its cap)

There is only one account, so there is no successor to hand over to — the office pauses
and resumes. When your burn says the wall is close:

1. Stop delegating. Write the `claude` lane into the park-file with the expected reset.
2. Let in-flight workers reach a clean boundary; release what has settled.
3. Write `~/.claude/orchestrator/briefs/<project>.md`: the term's Run id and the 5 lines
   — done / in-flight / changed / needs-decision / backlog head.
4. Rewrite the plaque: `OFFICE:president[<project>]=paused until <reset UTC> | reason:
   CC window | brief: ~/.claude/orchestrator/briefs/<project>.md | run: <run_id>`.
5. Tell the user the reset time and that any session can resume by taking office.

If a president freezes at the wall without pausing (accepted residual risk): after the
reset, start a session in the office worktree and take office — plaque + park-file +
`worktree ps` + the Run inbox carry everything needed. On resume, delete the brief file
once its contents are absorbed.

## Scripts

- `scripts/limits.sh [claude|burn|parked|all]` — quota snapshot (CC windows exact via
  `/usage`, burn-rate fallback; parked lanes from the shared park-file). Requires `jq`.
