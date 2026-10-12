#!/usr/bin/env -S uv run --script
# /// script
# requires-python = "==3.13.*"
# dependencies = []
# ///
import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from spec import Job, Spec, load_spec, ssh

SACCT_FIELDS = "JobID,State,ExitCode,ElapsedRaw,AllocCPUS,AllocTRES"
TERMINAL_OK = {"COMPLETED"}
ACTIVE = {"PENDING", "RUNNING", "REQUEUED", "COMPLETING"}
# array tasks waiting on these never start on their own
STUCK_REASONS = {"QOSGrpCPUMinutesLimit", "QOSGrpGRESRunMinutes"}


@dataclass
class Task:
    id: str
    state: str
    exit_code: str
    elapsed_s: int


@dataclass
class JobStatus:
    id: int
    label: str
    states: dict[str, int] = field(default_factory=dict)
    cpu_h: float = 0.0
    gpu_h: float = 0.0
    failed: list[Task] = field(default_factory=list)
    pending_reasons: dict[str, int] = field(default_factory=dict)


def _gpus(tres: str) -> int:
    m = re.search(r"gres/gpu=(\d+)", tres)
    return int(m.group(1)) if m else 0


def _collect(
    job: Job, sacct_rows: list[list[str]], squeue: list[str]
) -> JobStatus:
    status = JobStatus(job.id, job.label)
    states: Counter[str] = Counter()
    for job_id, state, exit_code, elapsed, cpus, tres in sacct_rows:
        if not job_id.startswith(f"{job.id}_") and job_id != str(job.id):
            continue
        state = state.split()[0]
        if state == "PENDING":
            continue  # sacct folds pending array tasks into one line
        states[state] += 1
        hours = int(elapsed or 0) / 3600
        status.cpu_h += int(cpus or 0) * hours
        status.gpu_h += _gpus(tres) * hours
        if state not in TERMINAL_OK | ACTIVE:
            status.failed.append(
                Task(job_id, state, exit_code, int(elapsed or 0))
            )
    reasons: Counter[str] = Counter()
    for line in squeue:
        task_id, state, reason = line.split("|")
        if task_id.split("_")[0] == str(job.id) and state == "PENDING":
            states["PENDING"] += 1
            reasons[reason] += 1
    status.states = dict(states)
    status.pending_reasons = dict(reasons)
    return status


def query(spec: Spec) -> list[JobStatus]:
    ids = ",".join(str(j.id) for j in spec.jobs)
    sacct = ssh(
        spec.ssh_host,
        f"sacct -j {ids} -X -n -P -o {SACCT_FIELDS}; echo '@@'; "
        f"squeue -r -j {ids} -h -o '%i|%T|%r' 2>/dev/null || true",
    )
    head, _, tail = sacct.partition("@@\n")
    rows = [r.split("|") for r in head.splitlines() if r.strip()]
    squeue = [r for r in tail.splitlines() if r.strip()]
    return [_collect(job, rows, squeue) for job in spec.jobs]


def _render(statuses: list[JobStatus]) -> list[str]:
    lines = []
    for s in statuses:
        counts = " ".join(f"{k}={v}" for k, v in sorted(s.states.items()))
        lines.append(
            f"{s.id:>9} {s.label:<28} {counts}  "
            f"cpu_h={s.cpu_h:.0f} gpu_h={s.gpu_h:.1f}"
        )
        for reason, n in s.pending_reasons.items():
            flag = (
                "  !! never starts, see wcss-slurm"
                if reason in STUCK_REASONS
                else ""
            )
            lines.append(f"{'':>10}pending {n} x {reason}{flag}")
        for t in s.failed:
            array_id, _, task = t.id.partition("_")
            lines.append(
                f"{'':>10}{t.state} {t.id} exit={t.exit_code} elapsed="
                f"{t.elapsed_s // 3600}h{t.elapsed_s % 3600 // 60:02d}m "
                f"log: logs/slurm-{array_id}_{task}.err"
            )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="SLURM state of an experiment")
    parser.add_argument("experiment", type=Path, help="experiment.toml")
    args = parser.parse_args()
    spec = load_spec(args.experiment)
    if not spec.jobs:
        print("no [[cluster.jobs]] recorded in", spec.path)
        return
    statuses = query(spec)
    total: Counter[str] = Counter()
    for s in statuses:
        total.update(s.states)
    active = sum(total[k] for k in ACTIVE)
    print(
        f"{spec.name} on {spec.ssh_host}: "
        + " ".join(f"{k}={v}" for k, v in sorted(total.items()))
        + f" | cpu_h={sum(s.cpu_h for s in statuses):.0f}"
        + f" gpu_h={sum(s.gpu_h for s in statuses):.1f}"
        + (" | ALL DONE" if active == 0 else f" | active={active}")
    )
    print("\n".join(_render(statuses)))
    spec.cache_dir.mkdir(parents=True, exist_ok=True)
    (spec.cache_dir / "cluster.json").write_text(
        json.dumps(
            {
                "checked": datetime.now().isoformat(timespec="minutes"),
                "jobs": [asdict(s) for s in statuses],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as e:
        sys.exit(f"error: {e}")
