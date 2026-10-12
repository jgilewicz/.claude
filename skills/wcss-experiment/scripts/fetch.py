#!/usr/bin/env -S uv run --script
# /// script
# requires-python = "==3.13.*"
# dependencies = ["wandb==0.30.0"]
# ///
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from runs import first_present, list_runs
from spec import Spec, load_spec


def _series(
    spec: Spec, rows: list[dict[str, Any]], keys: tuple[str, ...]
) -> dict[str, list[float]]:
    xs, ys = [], []
    for row in rows:
        x = first_present(row, spec.x_keys)
        y = first_present(row, keys)
        if x is not None and y is not None:
            xs.append(x)
            ys.append(y)
    return {"x": xs, "y": ys}


def _fetch_one(
    spec: Spec, key: tuple[str, str, int], run: Any
) -> dict[str, Any]:
    rows = list(run.scan_history(page_size=2000))
    cond, env, seed = key
    return {
        "id": run.id,
        "name": run.name,
        "url": run.url,
        "state": run.state,
        "created_at": run.created_at,
        "commit": (run.metadata or {}).get("git", {}).get("commit"),
        "condition": cond,
        "env": env,
        "seed": seed,
        "metric": _series(spec, rows, spec.metric_keys),
        "secondary": {
            s.key: _series(spec, rows, (s.key,)) for s in spec.secondary
        },
    }


def _is_fresh(path: Path, run: Any) -> bool:
    if not path.exists() or run.state == "running":
        return False
    return json.loads(path.read_text())["state"] == run.state


def main() -> None:
    parser = argparse.ArgumentParser(description="cache wandb histories")
    parser.add_argument("experiment", type=Path, help="experiment.toml")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    spec = load_spec(args.experiment)
    runs_dir = spec.cache_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    rs = list_runs(spec)
    todo = {
        key: run
        for key, run in rs.by_key.items()
        if not _is_fresh(runs_dir / f"{run.id}.json", run)
    }
    keep = {f"{run.id}.json" for run in rs.by_key.values()}
    for stale in runs_dir.glob("*.json"):
        if stale.name not in keep:
            stale.unlink()  # superseded duplicate or retagged run
    with ThreadPoolExecutor(args.workers) as pool:
        results = pool.map(lambda kv: _fetch_one(spec, *kv), todo.items())
        for record in results:
            (runs_dir / f"{record['id']}.json").write_text(json.dumps(record))
    (spec.cache_dir / "index.json").write_text(
        json.dumps(
            {
                "fetched": datetime.now().isoformat(timespec="minutes"),
                "unparsed": [r.name for r in rs.unparsed],
                "off_grid": [r.name for r in rs.off_grid],
                "duplicates": [r.name for r in rs.duplicates],
            },
            indent=1,
        )
    )
    print(
        f"{len(rs.by_key)} runs cached in {runs_dir} "
        f"({len(todo)} fetched, {len(rs.by_key) - len(todo)} unchanged); "
        f"skipped: {len(rs.unparsed)} unparsed, {len(rs.off_grid)} off-grid, "
        f"{len(rs.duplicates)} duplicates"
    )


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
