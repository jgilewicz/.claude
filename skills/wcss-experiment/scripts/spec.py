import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

SSH_OPTS = (
    "-o",
    "BatchMode=yes",
    "-o",
    "NumberOfPasswordPrompts=0",
    "-o",
    "ConnectTimeout=15",
)


@dataclass(frozen=True)
class Comparison:
    a: str
    b: str
    question: str


@dataclass(frozen=True)
class Secondary:
    key: str
    label: str
    note: str


@dataclass(frozen=True)
class Job:
    id: int
    label: str


@dataclass(frozen=True)
class Spec:
    path: Path
    name: str
    question: str
    entity: str
    project: str
    tag: str
    run_name: re.Pattern[str]
    envs: tuple[str, ...]
    conditions: tuple[str, ...]
    seeds: tuple[int, ...]
    total_steps: int
    metric_keys: tuple[str, ...]
    x_keys: tuple[str, ...]
    metric_label: str
    final_window: float
    reference: str
    thresholds: tuple[float, ...]
    comparisons: tuple[Comparison, ...]
    secondary: tuple[Secondary, ...]
    ssh_host: str
    jobs: tuple[Job, ...]

    @property
    def cache_dir(self) -> Path:
        return self.path.parent / "cache"

    @property
    def report_path(self) -> Path:
        return self.path.parent / "report.html"

    @property
    def wandb_path(self) -> str:
        return f"{self.entity}/{self.project}"


def _require(table: dict[str, Any], key: str, where: str, path: Path) -> Any:
    if key not in table:
        raise ValueError(f"{path}: missing `{key}` in {where}")
    return table[key]


def _check_names(spec: Spec) -> None:
    groups = set(spec.run_name.groupindex)
    if not {"condition", "env", "seed"} <= groups:
        raise ValueError(
            f"{spec.path}: wandb.run_name needs named groups "
            f"(?P<condition>...), (?P<env>...), (?P<seed>...); got {groups}"
        )
    named = [spec.reference]
    named += [c.a for c in spec.comparisons] + [c.b for c in spec.comparisons]
    unknown = sorted(set(named) - set(spec.conditions))
    if unknown:
        raise ValueError(
            f"{spec.path}: {unknown} used in [reference]/[[comparisons]] "
            f"but missing from `conditions`"
        )
    if not 0 < spec.final_window <= 1:
        raise ValueError(f"{spec.path}: metric.final_window must be in (0, 1]")
    if any(not 0 < t <= 1 for t in spec.thresholds):
        raise ValueError(f"{spec.path}: reference.thresholds must be in (0, 1]")


def load_spec(path: Path) -> Spec:
    try:
        raw = tomllib.loads(path.read_text())
    except FileNotFoundError as e:
        raise ValueError(
            f"no experiment file at {path}; create one from "
            "references/experiment-spec.md"
        ) from e
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"invalid TOML in {path}: {e}") from e
    wb = _require(raw, "wandb", "top level", path)
    metric = _require(raw, "metric", "top level", path)
    ref = _require(raw, "reference", "top level", path)
    cluster = raw.get("cluster", {})
    spec = Spec(
        path=path.resolve(),
        name=_require(raw, "name", "top level", path),
        question=raw.get("question", ""),
        entity=_require(wb, "entity", "[wandb]", path),
        project=_require(wb, "project", "[wandb]", path),
        tag=_require(wb, "tag", "[wandb]", path),
        run_name=re.compile(_require(wb, "run_name", "[wandb]", path)),
        envs=tuple(_require(raw, "envs", "top level", path)),
        conditions=tuple(_require(raw, "conditions", "top level", path)),
        seeds=tuple(_require(raw, "seeds", "top level", path)),
        total_steps=int(_require(raw, "total_steps", "top level", path)),
        metric_keys=tuple(_require(metric, "keys", "[metric]", path)),
        x_keys=tuple(_require(metric, "x", "[metric]", path)),
        metric_label=metric.get("label", metric["keys"][0]),
        final_window=float(metric.get("final_window", 0.1)),
        reference=_require(ref, "condition", "[reference]", path),
        thresholds=tuple(ref.get("thresholds", (0.25, 0.5, 0.75, 0.9))),
        comparisons=tuple(
            Comparison(c["a"], c["b"], c.get("question", ""))
            for c in raw.get("comparisons", [])
        ),
        secondary=tuple(
            Secondary(s["key"], s.get("label", s["key"]), s.get("note", ""))
            for s in raw.get("secondary", [])
        ),
        ssh_host=cluster.get("ssh_host", "wcss"),
        jobs=tuple(
            Job(int(j["id"]), j.get("label", ""))
            for j in cluster.get("jobs", [])
        ),
    )
    _check_names(spec)
    return spec


def parse_run_name(spec: Spec, name: str) -> tuple[str, str, int] | None:
    m = spec.run_name.match(name)
    if m is None:
        return None
    return m["condition"], m["env"], int(m["seed"])


def ssh(host: str, command: str) -> str:
    # never retry: three failed logins lock a WCSS account for 24 h
    result = subprocess.run(
        ["ssh", *SSH_OPTS, host, command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ssh {host} failed (exit {result.returncode}): "
            f"{result.stderr.strip()}. Do not retry in a loop; check the "
            "network/VPN and the key, see wcss-slurm references/access.md"
        )
    return result.stdout
