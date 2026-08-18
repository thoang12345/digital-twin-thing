# Battery-Bus Autonomous Digital Twin Handoff

This package is the curated, portable handoff for the LLM agent and the
battery-bus autonomous digital-twin experiment. It contains the runnable agent,
the tested Simulink variants, the matched baseline/LLM experiment scripts, the
recorded results, and a presentation that explains the system and its use.

The original working directory was not modified or reorganized. This folder is
a deployment copy intended to be moved to another Windows machine.

## Start here

1. Install Python 3.10 or newer, MATLAB/Simulink, and the electrical-toolbox
   dependencies used by the models.
2. Install LM Studio and download a compatible local chat model. The tested
   identifier is `llama-3-groq-8b-tool-use`.
3. Run `setup_environment.bat` from this folder.
4. Run `run_offline_smoke_test.bat` to verify the Python runner without MATLAB.
5. Open `presentation/Battery_Bus_Autonomy_Handoff_v2.pptx` for the architecture,
   tutorial, generic runner interface, experiment, and results walkthrough.
6. Follow `Modules/Digital_Twins/comparison_experiment/README.md` for the matched
   Simulink baseline-versus-LLM experiment.

## Main launchers

| File | Purpose |
|---|---|
| `setup_environment.bat` | Creates `.venv`, installs dependencies, and runs focused tests. |
| `start_assistant_gui.bat` | Starts the Tkinter assistant and Autonomous DT interface. |
| `start_assistant_cli.bat` | Starts the console assistant. |
| `run_offline_smoke_test.bat` | Runs a five-second deterministic mock mission. |
| `run_matlab_comparison.bat` | Runs the complete paced baseline and guarded LLM/UDP comparison. |
| `run_dt_runner.py` | Standalone autonomous DT runner entry point. |

## Generic Autonomous DT interface

The GUI is now a model-agnostic launcher and monitor. Its Autonomous DT area is
organized into four settings tabs:

| Tab | Owns |
|---|---|
| Run | Backend, policy, agent interval, duration, pacing, and output files. |
| Model Inputs | Runner script, model file/identifier, and one DT-specific CLI argument per line. |
| Connection | UDP endpoints, timeout/resend behavior, reset, and optional telemetry republish. |
| Agent | OpenAI-compatible endpoint, model/sampling settings, fallback behavior, and trace output. |

The live display follows `Agent request -> Runner output -> Local control -> DT
feedback`. These labels are generic; the runner supplies the displayed values
through versioned `DT_GUI_EVENT` console records. The delivered
`run_dt_runner.py` remains the battery-bus implementation. A different digital
twin can use the same GUI by providing a compatible runner and its own model
arguments; its local control logic remains inside that model.

## Important model files

The Simulink filenames retain their tested names because MATLAB scripts and
compiled model references depend on them. The legacy spelling in
`DT_enviroment...` is therefore intentional in this handoff copy.

| Model | Role |
|---|---|
| `Modules/Digital_Twins/DT_enviroment.slx` | Original digital-twin model retained as a reference. |
| `Modules/Digital_Twins/DT_enviroment_state_machine.slx` | Standalone model with the deterministic local supervisory state machine. |
| `Modules/Digital_Twins/DT_enviroment_state_machine_baseline_instrumented.slx` | Instrumented deterministic comparison case. |
| `Modules/Digital_Twins/DT_enviroment_state_machine_llm_udp.slx` | Instrumented guarded LLM/UDP comparison case. |

## Control concept

The LLM is a slow supervisory layer, not the fast electrical controller.

1. The LLM proposes a mode and power intent every 10 simulation seconds.
2. The Python runner validates and guards the proposal.
3. The Simulink state machine enforces final grid-level behavior every 1 ms.
4. The converter and electrical plant remain below that supervisory layer.

The agent therefore cannot bypass SOC limits, source headroom, no-backfeed
behavior, bus support, saturation, or stale-command fallback.

## Recorded result in this package

Both controllers were run on the same 120-second scenario: 200 W initial load,
500 W at 50 seconds, and 600 W at 100 seconds. The guarded LLM case completed
11 calls, recorded one malformed-response fallback, and continued bus support
without a safety stop. Its single-run bus-voltage RMSE was 0.0714 V versus
0.0853 V for the deterministic baseline; wall time was 152.94 seconds versus
149.26 seconds.

These are demonstration measurements from one machine, not statistical
performance claims. Repeat the experiment before reporting confidence
intervals or broad timing conclusions.

## Default network and timing contract

| Item | Default |
|---|---:|
| Python to Simulink command port | UDP 55000 |
| Simulink to Python observation port | UDP 55001 |
| Optional telemetry monitor port | UDP 55002 |
| LM Studio endpoint | `http://127.0.0.1:1234/v1` |
| Observation rate | 10 Hz |
| LLM decision interval | 10 simulation seconds |
| Local state-machine sample time | 1 ms |
| Stale-command fallback | 15 simulation seconds |

## Where to look next

- `PROJECT_MAP.md` describes the code layout and execution flow.
- `docs/autonomous_dt_runner.md` documents the standalone runner, GUI event
  contract, and live Simulink/UDP path.
- `docs/OPERATIONS_GUIDE.md` provides the staged setup and troubleshooting path.
- `results/comparison/experiment_summary.md` contains the complete result
  interpretation.
- `results/comparison/figures/` contains publication-ready PNG and PDF plots.
- `research/` contains the current paper draft and framework notes.
- `PACKAGE_MANIFEST.txt` lists every delivered file with its size.
