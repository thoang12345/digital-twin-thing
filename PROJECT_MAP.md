# Project Map

## Agent path

```text
assistant_cli.py / assistant_gui.py
  -> Modules/Core/bootstrap.py
     -> Modules/Core/conversationloop.py
        -> Modules/Prompt/prompt.py
        -> Modules/Chat_Memory/Chat_Memory.py
        -> Modules/RAG/* and chroma_db/
        -> Modules/Tools/Tool_loop.py
           -> Modules/Tools/tool_catalog.py
              -> run_autonomous_DT
                 -> Modules/Digital_Twins/tool_runner.py
```

The assistant uses an OpenAI-compatible endpoint. Its defaults live in
`Modules/Core/settings.py`: LM Studio on port 1234, the tested local model, the
local Chroma runtime store, zero temperature, and a bounded tool loop. The
delivered store starts empty so it contains no machine-specific source paths.

## Autonomous digital-twin path

```text
run_dt_runner.py
  -> Modules/Digital_Twins/runner_cli.py
     -> Modules/Digital_Twins/gui_events.py (optional GUI summaries)
     -> backend: mock | UDP | MATLAB Engine
     -> policy: deterministic | LLM
     -> Modules/Digital_Twins/constraints.py
     -> UDP command to Simulink
     -> CSV + Markdown report + JSONL LLM trace
```

Key modules:

| Module | Responsibility |
|---|---|
| `types.py` | Observation, command, goal, event, and mission data contracts. |
| `backends.py` | Mock and MATLAB Engine backend implementations. |
| `udp_backend.py` | Live observation receive and command transmit loop. |
| `udp_protocol.py` | Compact JSON datagram contract. |
| `policy.py` | Deterministic and OpenAI-compatible LLM policies plus fallback. |
| `constraints.py` | Deterministic power, SOC, source, slew, and safety guards. |
| `runner.py` | Mission state loop and event recording. |
| `runner_cli.py` | Command-line contract, backend/policy assembly, and optional GUI-event emission. |
| `gui_events.py` | Versioned `DT_GUI_EVENT` summaries used by the generic live display. |
| `reporting.py` | CSV and Markdown result artifacts. |
| `tool_runner.py` | Adapter used by the general assistant tool catalog. |

## Generic GUI launcher path

```text
Autonomous DT GUI
  -> choose runner script + model
  -> append DT-specific CLI arguments
  -> launch runner with --emit-gui-events
  -> parse DT_GUI_EVENT v1 summaries
  -> display Agent request -> Runner output -> Local control -> DT feedback
```

The GUI owns launching, connection configuration, process control, and generic
status presentation. The selected runner owns the digital-twin-specific
arguments and the meaning of its summaries. The model retains local control
and safety authority. The included `run_dt_runner.py` is the battery-bus runner,
not a universal plant implementation.

## Simulink comparison path

```text
run_full_comparison.m
  -> build_llm_udp_comparison_models.m
  -> ensure_lm_studio_headless.m
  -> run_baseline_experiment.m
  -> start_llm_supervisor.m
  -> run_llm_udp_experiment.m
  -> finish_llm_supervisor.m
  -> plot_llm_udp_comparison.m
```

The two comparison models share the same electrical plant, load profile,
battery interface, controller sampling, limits, and instrumentation. Only the
supervisory intent source differs.

## Authority and time scales

| Layer | Typical rate | Authority |
|---|---:|---|
| LLM supervisor | 10 s | Proposes `CHARGE`, `HOLD`, `DISCHARGE`, or `SAFE` and a power value. |
| Python guard | on each LLM decision | Validates schema and enforces policy/safety constraints. |
| Simulink grid state machine | 1 ms | Selects the final local mode and battery power reference. |
| Converter/electrical plant | fast/continuous model dynamics | Executes the feasible command and determines bus response. |

## Delivered data

- Full 1 ms baseline and LLM/UDP CSV logs.
- MATLAB timing tables and one-second CPU samples.
- Python decision log and Markdown mission report.
- Raw LLM request/response/fallback JSONL trace.
- Performance and timing summary tables.
- Five comparison figures in PNG and PDF form.
