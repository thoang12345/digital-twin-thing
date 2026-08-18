# Operations Guide

## 1. Verify the Python side

Run:

```bat
setup_environment.bat
run_offline_smoke_test.bat
```

A successful smoke test creates `logs/dt_runner_mock_smoke.csv` and
`logs/dt_runner_mock_smoke_report.md`.

## 2. Verify the standalone Simulink controller

In MATLAB:

```matlab
dtDir = fullfile(pwd,'Modules','Digital_Twins');
addpath(dtDir)
cd(dtDir)
run_state_machine_dt_smoke
```

The model should run without an LLM or UDP process. Its operating-state code is:

| Code | State |
|---:|---|
| 0 | HOLD |
| 1 | CHARGE |
| 2 | BUS_SUPPORT |
| 3 | SAFE_LOCAL |

## 3. Run the matched experiment

Install LM Studio, make sure its command-line tool is available under the
current Windows user profile, and make sure the tested local model is present.
Then run:

```bat
run_matlab_comparison.bat
```

The MATLAB workflow starts the local server, loads the model, runs both cases,
and writes a new result set to `results/latest_comparison/`.

## 4. Use the general agent interface

Run `start_assistant_gui.bat`. The Autonomous DT interface is a generic runner
launcher rather than a battery-specific control panel:

1. In **Run**, choose the backend and policy, agent interval, duration, pacing,
   and output paths.
2. In **Model Inputs**, choose the runner script and model, then add any
   digital-twin-specific CLI arguments one per line.
3. In **Connection**, configure UDP endpoints, timeouts, resend/reset behavior,
   and optional telemetry republishing.
4. In **Agent**, configure the OpenAI-compatible endpoint, model, sampling,
   fallback behavior, and JSONL trace.

The command preview shows exactly what will be launched. The live control path
shows `Agent request -> Runner output -> Local control -> DT feedback` using
versioned summaries emitted by the runner. The delivered `run_dt_runner.py`
supplies battery-bus summaries and remains available directly from the command
line. To reuse the GUI for another digital twin, supply a compatible runner
that accepts the common launcher flags and emits `DT_GUI_EVENT` version 1
records; keep plant-specific control and safety in that digital twin.

The agent tool name is `run_autonomous_DT`. It is registered in
`Modules/Tools/tool_catalog.py` and calls
`Modules/Digital_Twins/tool_runner.py`.

## 5. Troubleshooting

### No UDP observations

- Start Simulink before the Python UDP runner.
- Confirm observation port 55001 and command port 55000.
- Confirm no second process is already bound to port 55001.
- Allow MATLAB and Python through Windows Firewall.
- Keep compact telemetry below 512 bytes per datagram.

### LM Studio receives no calls

- Confirm policy mode is `llm`.
- Confirm `http://127.0.0.1:1234/v1` is reachable.
- Confirm the loaded model identifier matches the runner argument.
- Wait for a valid observation and the next 10-second policy tick.

### A malformed LLM response appears

This is expected to fail safely. The runner records a fallback and substitutes
the deterministic policy. The local state machine continues enforcing bus
support and safety.

### MATLAB cannot find a System object

Add both folders before loading the model:

```matlab
addpath(fullfile(pwd,'Modules','Digital_Twins'))
addpath(fullfile(pwd,'Modules','Digital_Twins','comparison_experiment'))
```

## 6. Before using results in a paper

Run repeated trials, record machine and software versions, preserve raw JSONL
and CSV logs, and report distributions or confidence intervals for latency and
CPU measurements. The delivered comparison is a validated single-run case.
