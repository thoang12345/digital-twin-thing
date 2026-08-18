# Matched Baseline and Guarded LLM/UDP Experiment

This folder reproduces the 120-second comparison delivered in
`results/comparison/`. Both Simulink cases retain the same plant, load profile,
battery path, 1 ms local state-machine loop, limits, and logging.

## One-command run

From the package root:

```bat
run_matlab_comparison.bat
```

Or from MATLAB:

```matlab
cd(fullfile(pwd,'Modules','Digital_Twins','comparison_experiment'))
[timing, performance] = run_full_comparison
```

The workflow starts the LM Studio local server if needed, loads the tested
model, runs the deterministic case, runs the live UDP case, records process and
system timing, and regenerates the tables and figures.

New outputs are written to `results/latest_comparison/`. The original recorded
run remains unchanged in `results/comparison/`.

## Key scripts

| Script | Purpose |
|---|---|
| `run_full_comparison.m` | Complete build/run/plot workflow. |
| `build_llm_udp_comparison_models.m` | Rebuilds the two experiment model copies. |
| `run_baseline_experiment.m` | Runs the deterministic reference case. |
| `run_llm_udp_experiment.m` | Runs the LLM/UDP case while the Python supervisor is active. |
| `plot_llm_udp_comparison.m` | Regenerates performance, timing, and audit figures. |
| `start_llm_supervisor.m` | Starts the Python runner as a hidden process. |
| `sample_cpu_usage.ps1` | Samples system, MATLAB, Python, and LM Studio CPU use. |

The UDP payload is deliberately kept below 512 bytes for reliable Windows
operation. Full-resolution data remains in the CSV logs.

