from dataclasses import dataclass
from typing import Any

import wandb

from spec import Spec, parse_run_name

Key = tuple[str, str, int]


@dataclass
class RunSet:
    by_key: dict[Key, Any]
    duplicates: list[Any]
    unparsed: list[Any]
    off_grid: list[Any]


def _preferred(a: Any, b: Any) -> Any:
    rank_a = (a.state == "finished", a.created_at)
    rank_b = (b.state == "finished", b.created_at)
    return a if rank_a >= rank_b else b


def list_runs(spec: Spec) -> RunSet:
    api = wandb.Api(timeout=60)
    runs = api.runs(
        spec.wandb_path, filters={"tags": {"$in": [spec.tag]}}, per_page=500
    )
    out = RunSet({}, [], [], [])
    for run in runs:
        key = parse_run_name(spec, run.name)
        if key is None:
            out.unparsed.append(run)
            continue
        cond, env, seed = key
        if (
            cond not in spec.conditions
            or env not in spec.envs
            or seed not in spec.seeds
        ):
            out.off_grid.append(run)
            continue
        if key in out.by_key:
            keep = _preferred(out.by_key[key], run)
            out.duplicates.append(
                run if keep is out.by_key[key] else out.by_key[key]
            )
            run = keep
        out.by_key[key] = run
    return out


def expected_keys(spec: Spec) -> list[Key]:
    return [
        (c, e, s)
        for e in spec.envs
        for c in spec.conditions
        for s in spec.seeds
    ]


def first_present(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for k in keys:
        value = row.get(k)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None
