# experiment.toml

**TL;DR**: one file per experiment, read by all four scripts. The grid
(`envs` × `conditions` × `seeds`) is what "complete" is measured against; the
wandb tag selects the runs; `run_name` maps a run to its grid cell.

## Schema

```toml
name = "thesis-v1"                       # page title, record name
question = "Does the uncertainty gate select better individuals than a random gate at equal cost?"

envs = ["HalfCheetah-v5", "dog-stand"]   # order = table/plot order
conditions = ["erl", "sc_erl-random", "sc_erl-ensemble", "sc_erl-ensemble-rgate"]
# order also picks colours: the first 8 get categorical hues in "All
# conditions" plots, the rest are grey context lines
seeds = [0, 1, 2, 3, 4]
total_steps = 1_000_000                  # per-run budget on the x-axis

[wandb]
entity = "evo_rl"
project = "triage_erl"
tag = "thesis-v1"                        # every run of the experiment, and nothing else
# named groups condition, env, seed are required
run_name = '^(?P<condition>.+)_(?P<env>[^_]+)_s(?P<seed>\d+)$'

[metric]
keys = ["perf/eval_rl", "eval_reward"]   # first key present in a history row wins
x = ["env_steps", "total_steps"]         # same rule; the x-axis of every claim
label = "eval return"
final_window = 0.1                       # final score = mean over the last 10 %

[reference]
condition = "erl"                        # speed-to-threshold baseline
thresholds = [0.25, 0.5, 0.75, 0.9]

[[comparisons]]                          # pre-registered; Holm runs across these
a = "sc_erl-ensemble"
b = "sc_erl-ensemble-rgate"
question = "Uncertainty gate vs random gate, same critic"

[[secondary]]                            # reported, not tested
key = "cost/real_frac"
label = "real_frac"
note = "share evaluated for real; lower = cheaper"

[cluster]
ssh_host = "wcss"                        # SSH alias with BatchMode=yes

[[cluster.jobs]]                         # appended at submission, one per sbatch
id = 1234567
label = "HalfCheetah-v5"

[report]
url = ""                                 # Artifact URL after the first publish
```

`load_spec` fails fast with the file and key when something is missing, when
`run_name` lacks a named group, or when a comparison/reference names a
condition not in `conditions`.

## Job-script contract

What the scripts assume about the runs. A job script that breaks one of these
produces a report with silent gaps.

- **One tag per experiment** in `wandb.init(tags=...)`, the same string as
  `[wandb] tag`. Re-using a tag across experiments mixes their runs.
- **Run names encode the grid cell** and `run_name` parses them. Runs that do
  not parse show up as `UNPARSED`; cells outside the grid as `OFF-GRID`.
- **`WANDB_MODE=online`** in the job. Offline runs reach wandb only when
  synced, so supervision sees nothing until a run ends.
- **The x key is logged in every row that carries the metric**, e.g. via
  `wandb.define_metric("*", step_metric="env_steps")` or a payload that
  includes it. Rows without an x value are dropped.
- **A resubmitted cell keeps its run name.** The newest finished run wins;
  older ones are listed as duplicates.
- `WANDB_API_KEY` exported on the login node before `sbatch`; never written
  into the job script or the toml.

## Example: usc_erl_jax

`slurm_run_array.sh` names runs `<condition>_<env>_s<seed>` and tags them
`[TAG, condition, env]`, so the `run_name` above parses them as is. SBX
baselines log `eval_reward` against `total_steps`; ERL/SC-ERL log
`perf/eval_rl` against `env_steps`, hence the two-key lists in `[metric]`.
