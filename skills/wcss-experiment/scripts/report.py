#!/usr/bin/env -S uv run --script
# /// script
# requires-python = "==3.13.*"
# dependencies = ["numpy==2.5.3", "scipy==1.18.1"]
# ///
import argparse
import html
import json
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from spec import Spec, load_spec

TEMPLATE = Path(__file__).with_name("report_template.html")
BOOTSTRAP = 2000
GRID_POINTS = 60
ALPHA = 0.05
MIN_ENVS_FOR_TEST = 6  # Wilcoxon on n < 6 pairs cannot reach p < 0.05


@dataclass
class RunData:
    name: str
    url: str
    state: str
    commit: str | None
    cond: str
    env: str
    seed: int
    x: np.ndarray
    y: np.ndarray
    secondary: dict[str, tuple[np.ndarray, np.ndarray]]
    complete: bool
    final: float


def _arrays(series: dict[str, list[float]]) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(series["x"], dtype=float)
    y = np.asarray(series["y"], dtype=float)
    order = np.argsort(x, kind="stable")
    return x[order], y[order]


def window_mean(spec: Spec, x: np.ndarray, y: np.ndarray) -> float:
    mask = (x >= (1 - spec.final_window) * spec.total_steps) & np.isfinite(y)
    return float(y[mask].mean()) if mask.any() else math.nan


def load_runs(spec: Spec) -> list[RunData]:
    runs_dir = spec.cache_dir / "runs"
    if not runs_dir.is_dir():
        raise ValueError(f"no cache at {runs_dir}; run fetch.py first")
    runs = []
    for path in sorted(runs_dir.glob("*.json")):
        rec = json.loads(path.read_text())
        x, y = _arrays(rec["metric"])
        complete = bool(len(x) and x[-1] >= 0.99 * spec.total_steps)
        runs.append(
            RunData(
                name=rec["name"],
                url=rec["url"],
                state=rec["state"],
                commit=rec.get("commit"),
                cond=rec["condition"],
                env=rec["env"],
                seed=rec["seed"],
                x=x,
                y=y,
                secondary={k: _arrays(v) for k, v in rec["secondary"].items()},
                complete=complete,
                final=window_mean(spec, x, y) if complete else math.nan,
            )
        )
    return runs


def ci95(values: np.ndarray) -> float:
    if len(values) < 2:
        return math.nan
    sem = values.std(ddof=1) / math.sqrt(len(values))
    return float(stats.t.ppf(0.975, len(values) - 1) * sem)


def finals(runs: list[RunData], cond: str, env: str) -> np.ndarray:
    vals = [r.final for r in runs if r.cond == cond and r.env == env]
    return np.asarray([v for v in vals if math.isfinite(v)])


def env_table(spec: Spec, runs: list[RunData]) -> dict[str, Any]:
    cells: dict[str, dict[str, Any]] = {}
    bounds: dict[str, tuple[float, float]] = {}
    for env in spec.envs:
        row = {}
        for cond in spec.conditions:
            v = finals(runs, cond, env)
            row[cond] = {
                "mean": float(v.mean()) if len(v) else math.nan,
                "std": float(v.std(ddof=1)) if len(v) > 1 else math.nan,
                "ci": ci95(v),
                "n": len(v),
            }
        means = [c["mean"] for c in row.values() if math.isfinite(c["mean"])]
        lo, hi = (min(means), max(means)) if means else (math.nan, math.nan)
        bounds[env] = (lo, hi)
        for c in row.values():
            c["norm"] = normalize(c["mean"], lo, hi)
        cells[env] = row
    return {"cells": cells, "bounds": bounds}


def normalize(value: float, lo: float, hi: float) -> float:
    if not (math.isfinite(value) and hi > lo):
        return math.nan
    return (value - lo) / (hi - lo)


def iqm_with_ci(
    per_env: list[np.ndarray], rng: np.random.Generator
) -> tuple[float, float, float]:
    per_env = [a for a in per_env if len(a)]
    if not per_env:
        return math.nan, math.nan, math.nan
    point = float(stats.trim_mean(np.concatenate(per_env), 0.25))
    # stratified bootstrap: resample seeds within each env
    boot = np.concatenate(
        [a[rng.integers(0, len(a), (BOOTSTRAP, len(a)))] for a in per_env],
        axis=1,
    )
    dist = stats.trim_mean(boot, 0.25, axis=1)
    lo, hi = np.percentile(dist, [2.5, 97.5])
    return point, float(lo), float(hi)


def aggregate(
    spec: Spec, runs: list[RunData], table: dict[str, Any]
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(0)
    rows = []
    for cond in spec.conditions:
        per_env = []
        for env in spec.envs:
            lo, hi = table["bounds"][env]
            v = np.asarray(
                [normalize(f, lo, hi) for f in finals(runs, cond, env)]
            )
            per_env.append(v[np.isfinite(v)])
        iqm, lo, hi = iqm_with_ci(per_env, rng)
        rows.append(
            {
                "condition": cond,
                "iqm": iqm,
                "lo": lo,
                "hi": hi,
                "runs": int(sum(len(a) for a in per_env)),
                "envs": int(sum(1 for a in per_env if len(a))),
            }
        )
    return rows


def prob_greater(a: np.ndarray, b: np.ndarray) -> float:
    diff = a[:, None] - b[None, :]
    return float(((diff > 0) + 0.5 * (diff == 0)).mean())


def _env_comparison(
    a: np.ndarray, b: np.ndarray, lo: float, hi: float
) -> dict[str, Any]:
    p = math.nan
    if len(a) > 1 and len(b) > 1:
        p = float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    return {
        "a": float(a.mean()),
        "b": float(b.mean()),
        "diff_norm": (a.mean() - b.mean()) / (hi - lo) if hi > lo else 0.0,
        "p_a_gt_b": prob_greater(a, b),
        "p_mwu": p,
    }


def compare_pair(
    spec: Spec, runs: list[RunData], table: dict[str, Any], a: str, b: str
) -> dict[str, Any]:
    per_env = {}
    for env in spec.envs:
        fa, fb = finals(runs, a, env), finals(runs, b, env)
        if len(fa) and len(fb):
            per_env[env] = _env_comparison(fa, fb, *table["bounds"][env])
    diffs = np.asarray([e["diff_norm"] for e in per_env.values()])
    p = math.nan
    if len(diffs) >= MIN_ENVS_FOR_TEST and np.any(diffs != 0):
        p = float(stats.wilcoxon(diffs).pvalue)
    return {
        "a": a,
        "b": b,
        "envs": len(per_env),
        "wins": int((diffs > 0).sum()),
        "losses": int((diffs < 0).sum()),
        "median_diff": float(np.median(diffs)) if len(diffs) else math.nan,
        "p_a_gt_b": float(np.mean([e["p_a_gt_b"] for e in per_env.values()]))
        if per_env
        else math.nan,
        "p": p,
        "per_env": per_env,
    }


def holm(pvalues: list[float]) -> list[float]:
    finite = sorted((p, i) for i, p in enumerate(pvalues) if math.isfinite(p))
    adjusted = [math.nan] * len(pvalues)
    running = 0.0
    for rank, (p, i) in enumerate(finite):
        running = max(running, min(1.0, (len(finite) - rank) * p))
        adjusted[i] = running
    return adjusted


def verdict(c: dict[str, Any]) -> str:
    if not math.isfinite(c["p_holm"]):
        return "untestable"
    if c["p_holm"] >= ALPHA:
        return "no difference"
    return "a better" if c["median_diff"] > 0 else "b better"


def comparisons(
    spec: Spec, runs: list[RunData], table: dict[str, Any]
) -> list[dict[str, Any]]:
    out = [compare_pair(spec, runs, table, c.a, c.b) for c in spec.comparisons]
    adjusted = holm([c["p"] for c in out])
    for c, spec_c, p_holm in zip(out, spec.comparisons, adjusted, strict=True):
        c["question"] = spec_c.question
        c["p_holm"] = p_holm
        c["verdict"] = verdict(c)
    return out


def steps_to(x: np.ndarray, y: np.ndarray, target: float) -> float | None:
    if len(y) >= 3:
        y = np.convolve(
            y, np.ones(3) / 3, mode="valid"
        )  # damp single noisy evals
        x = x[2:]
    hit = np.flatnonzero(y >= target)
    return float(x[hit[0]]) if len(hit) else None


def median_steps(runs: list[RunData], target: float) -> float | None:
    steps = [steps_to(r.x, r.y, target) for r in runs]
    reached = [s for s in steps if s is not None]
    # a condition "reaches" a threshold only if most of its seeds do
    if not runs or len(reached) * 2 < len(runs):
        return None
    return float(np.median(reached))


def _env_speedups(
    spec: Spec, runs: list[RunData], ref_final: float, env: str, frac: float
) -> dict[str, float | None]:
    env_runs = [r for r in runs if r.env == env and r.complete]
    start = float(np.median([r.y[0] for r in env_runs]))
    target = start + frac * (ref_final - start)
    ref_steps = median_steps(
        [r for r in env_runs if r.cond == spec.reference], target
    )
    out: dict[str, float | None] = {}
    for cond in spec.conditions:
        steps = median_steps([r for r in env_runs if r.cond == cond], target)
        out[cond] = ref_steps / steps if ref_steps and steps else None
    return out


def speedup(
    spec: Spec, runs: list[RunData], table: dict[str, Any]
) -> dict[str, Any]:
    eligible = []
    skipped = []
    for env in spec.envs:
        ref = table["cells"][env][spec.reference]["mean"]
        env_runs = [r for r in runs if r.env == env and r.complete]
        start = np.median([r.y[0] for r in env_runs]) if env_runs else math.nan
        (eligible if math.isfinite(ref) and ref > start else skipped).append(
            env
        )
    rows = {cond: [] for cond in spec.conditions}
    for frac in spec.thresholds:
        per_env = [
            _env_speedups(
                spec, runs, table["cells"][e][spec.reference]["mean"], e, frac
            )
            for e in eligible
        ]
        for cond in spec.conditions:
            vals = [v for s in per_env if (v := s[cond]) is not None]
            rows[cond].append(
                {
                    "median": statistics.median(vals) if vals else math.nan,
                    "envs": len(vals),
                }
            )
    return {"eligible": eligible, "skipped": skipped, "rows": rows}


def secondary(spec: Spec, runs: list[RunData]) -> list[dict[str, Any]]:
    out = []
    for s in spec.secondary:
        per_cond = {}
        for cond in spec.conditions:
            vals = [
                window_mean(spec, *r.secondary[s.key])
                for r in runs
                if r.cond == cond and r.complete and s.key in r.secondary
            ]
            v = np.asarray([x for x in vals if math.isfinite(x)])
            per_cond[cond] = {
                "mean": float(v.mean()) if len(v) else math.nan,
                "ci": ci95(v),
                "n": len(v),
            }
        out.append(
            {
                "key": s.key,
                "label": s.label,
                "note": s.note,
                "by_condition": per_cond,
            }
        )
    return out


def curves(spec: Spec, runs: list[RunData]) -> dict[str, Any]:
    grid = np.linspace(
        spec.total_steps / GRID_POINTS, spec.total_steps, GRID_POINTS
    )
    out: dict[str, dict[str, Any]] = {}
    for env in spec.envs:
        out[env] = {}
        for cond in spec.conditions:
            rows = [
                np.where(
                    (grid >= r.x[0]) & (grid <= r.x[-1]),
                    np.interp(grid, r.x, r.y),
                    np.nan,
                )
                for r in runs
                if r.env == env and r.cond == cond and len(r.x)
            ]
            if not rows:
                continue
            m = np.vstack(rows)
            n = np.isfinite(m).sum(axis=0)
            mean = np.nanmean(np.where(n > 0, m, 0.0), axis=0)
            half = [ci95(col[np.isfinite(col)]) for col in m.T]
            out[env][cond] = {
                "mean": [
                    _round(v) if k else None
                    for v, k in zip(mean, n, strict=True)
                ],
                "ci": [_round(h) for h in half],
                "n": n.tolist(),
            }
    return {"grid": grid.tolist(), "envs": out}


def _round(v: float) -> float | None:
    return float(f"{v:.4g}") if math.isfinite(v) else None


def health(spec: Spec, runs: list[RunData]) -> dict[str, Any]:
    seen = {(r.cond, r.env, r.seed) for r in runs}
    missing = [
        f"{c}/{e}/s{s}"
        for e in spec.envs
        for c in spec.conditions
        for s in spec.seeds
        if (c, e, s) not in seen
    ]
    incomplete = [
        {
            "name": r.name,
            "state": r.state,
            "progress": float(r.x[-1] / spec.total_steps) if len(r.x) else 0.0,
            "url": r.url,
        }
        for r in runs
        if not r.complete
    ]
    index_path = spec.cache_dir / "index.json"
    cluster_path = spec.cache_dir / "cluster.json"
    return {
        "expected": len(spec.envs) * len(spec.conditions) * len(spec.seeds),
        "complete": sum(r.complete for r in runs),
        "missing": missing,
        "incomplete": incomplete,
        "index": json.loads(index_path.read_text())
        if index_path.exists()
        else {},
        "cluster": json.loads(cluster_path.read_text())
        if cluster_path.exists()
        else None,
        "commits": sorted({r.commit[:7] for r in runs if r.commit}),
    }


def build(spec: Spec) -> dict[str, Any]:
    runs = load_runs(spec)
    table = env_table(spec, runs)
    return {
        "meta": {
            "name": spec.name,
            "question": spec.question,
            "wandb": f"https://wandb.ai/{spec.wandb_path}",
            "tag": spec.tag,
            "generated": datetime.now().isoformat(timespec="minutes"),
            "total_steps": spec.total_steps,
            "metric": spec.metric_label,
            "metric_keys": spec.metric_keys,
            "final_window": spec.final_window,
            "reference": spec.reference,
            "thresholds": spec.thresholds,
            "conditions": spec.conditions,
            "envs": spec.envs,
            "seeds": len(spec.seeds),
        },
        "health": health(spec, runs),
        "table": table["cells"],
        "aggregate": aggregate(spec, runs, table),
        "comparisons": comparisons(spec, runs, table),
        "speedup": speedup(spec, runs, table),
        "secondary": secondary(spec, runs),
        "curves": curves(spec, runs),
    }


def clean(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def summary(data: dict[str, Any]) -> str:
    h = data["health"]
    lines = [
        f"{data['meta']['name']}: "
        f"{h['complete']}/{h['expected']} runs complete, "
        f"{len(h['missing'])} missing, {len(h['incomplete'])} incomplete"
    ]
    ranked = sorted(
        (r for r in data["aggregate"] if math.isfinite(r["iqm"])),
        key=lambda r: -r["iqm"],
    )
    lines.append(
        "IQM (0 = worst, 1 = best condition per env): "
        + ", ".join(f"{r['condition']} {r['iqm']:.2f}" for r in ranked)
    )
    for c in data["comparisons"]:
        lines.append(
            f"{c['a']} vs {c['b']}: {c['verdict']} | wins {c['wins']}/"
            f"{c['envs']} envs, P(a>b)={c['p_a_gt_b']:.2f}, "
            f"p_holm={c['p_holm']:.3g}"
        )
    return "\n".join(lines)


def render(data: dict[str, Any]) -> str:
    payload = json.dumps(clean(data), allow_nan=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c")
    page = TEMPLATE.read_text()
    page = page.replace("__TITLE__", html.escape(data["meta"]["name"]))
    return page.replace('"__REPORT_DATA__"', payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="build the HTML report")
    parser.add_argument("experiment", type=Path, help="experiment.toml")
    args = parser.parse_args()
    spec = load_spec(args.experiment)
    data = build(spec)
    spec.report_path.write_text(render(data))
    print(summary(data))
    print(f"report: {spec.report_path}")


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
