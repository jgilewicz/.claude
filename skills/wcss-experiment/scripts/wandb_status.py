#!/usr/bin/env -S uv run --script
# /// script
# requires-python = "==3.13.*"
# dependencies = ["wandb==0.30.0"]
# ///
import argparse
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from runs import RunSet, expected_keys, first_present, list_runs
from spec import Spec, load_spec


def _progress(spec: Spec, run: Any) -> float:
    x = first_present(dict(run.summary), spec.x_keys)
    return 0.0 if x is None else min(x / spec.total_steps, 1.0)


def _minutes_since_log(run: Any) -> float:
    stamp = run.summary.get("_timestamp")
    return math.inf if stamp is None else (time.time() - float(stamp)) / 60


def _attention(spec: Spec, rs: RunSet, stall_min: float) -> list[str]:
    lines = []
    for (cond, env, seed), run in sorted(rs.by_key.items()):
        name = f"{cond}/{env}/s{seed}"
        pct = f"{_progress(spec, run):.0%}"
        if run.state in ("crashed", "failed", "killed"):
            lines.append(f"{run.state.upper():8} {name} at {pct}  {run.url}")
        elif run.state == "running" and _minutes_since_log(run) > stall_min:
            ago = _minutes_since_log(run)
            lines.append(
                f"STALLED  {name} at {pct}, no log for {ago:.0f} min  {run.url}"
            )
        metric = first_present(dict(run.summary), spec.metric_keys)
        if metric is not None and not math.isfinite(metric):
            lines.append(
                f"NONFINITE {name} {spec.metric_keys[0]}={metric}  {run.url}"
            )
    for run in rs.unparsed:
        lines.append(
            f"UNPARSED name `{run.name}` does not match wandb.run_name"
        )
    for run in rs.off_grid:
        lines.append(f"OFF-GRID `{run.name}` (condition/env/seed not in spec)")
    for run in rs.duplicates:
        lines.append(f"DUPLICATE `{run.name}` ({run.state}) ignored  {run.url}")
    return lines


def _by_condition(spec: Spec, rs: RunSet) -> list[str]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for (cond, _, _), run in rs.by_key.items():
        groups[cond].append(run)
    per_cond = len(spec.envs) * len(spec.seeds)
    width = max(len(c) for c in spec.conditions)
    lines = [
        f"{'condition':<{width}}  seen  fin  run  bad  progress  "
        f"{spec.metric_label} (median latest)"
    ]
    for cond in spec.conditions:
        runs = groups.get(cond, [])
        states = Counter(r.state for r in runs)
        bad = states["crashed"] + states["failed"] + states["killed"]
        prog = [_progress(spec, r) for r in runs]
        vals = [first_present(dict(r.summary), spec.metric_keys) for r in runs]
        finite = [v for v in vals if v is not None and math.isfinite(v)]
        lines.append(
            f"{cond:<{width}}  {len(runs):>3}/{per_cond:<3}"
            f"{states['finished']:>3} {states['running']:>4} {bad:>4}  "
            f"{statistics.median(prog) if prog else 0:>7.0%}  "
            f"{statistics.median(finite) if finite else float('nan'):>10.1f}"
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="wandb state of an experiment")
    parser.add_argument("experiment", type=Path, help="experiment.toml")
    parser.add_argument(
        "--stall-min",
        type=float,
        default=30,
        help="running runs silent this long are flagged (default 30)",
    )
    args = parser.parse_args()
    spec = load_spec(args.experiment)
    rs = list_runs(spec)
    states = Counter(r.state for r in rs.by_key.values())
    expected = len(expected_keys(spec))
    print(
        f"{spec.name} | {spec.wandb_path} tag={spec.tag} | "
        f"{len(rs.by_key)}/{expected} runs seen | "
        + "".join(f"{k}={v} " for k, v in sorted(states.items()))
        + f"| not started={expected - len(rs.by_key)}"
    )
    print("\n".join(_by_condition(spec, rs)))
    attention = _attention(spec, rs, args.stall_min)
    print("\nneeds attention:" if attention else "\nnothing needs attention")
    print("\n".join(attention))


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
