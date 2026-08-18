# Deterministic State Machine versus LLM/UDP Trial

## Experiment

Both controllers were run against the same 120 s Simulink plant and load
profile. The initial load was 200 W, increased to 500 W at 50 s, and increased
to 600 W at 100 s. Simulink was paced at 1x and the local electrical and
state-machine control ran at 1 ms in both cases.

The deterministic model used a fixed 100 W charge intent. The LLM case used
the local `llama-3-groq-8b-tool-use` model through LM Studio, with observations
sent at 10 Hz and supervisory decisions requested every 10 simulation seconds.

## Principal results

| Metric | Deterministic | LLM/UDP guarded |
|---|---:|---:|
| Bus-voltage minimum (V) | 396.804 | 397.855 |
| Bus-voltage maximum (V) | 401.177 | 400.786 |
| Bus-voltage RMSE from 400 V (V) | 0.0853 | 0.0714 |
| Battery-reference range (W) | -100 to 125 | -100 to 125 |
| SOC change (percentage points) | +0.00249 | -0.00018 |
| State transitions | 1 | 3 |
| SAFE_LOCAL duration (s) | 0 | 0.2 |
| Wall time (s) | 149.26 | 152.94 |
| MATLAB CPU time (s) | 137.38 | 146.77 |
| Average whole-system CPU (%) | 14.46 | 18.50 |
| LM Studio CPU during run (s) | 0.14 | 15.95 |
| LLM calls | 0 | 11 |
| Mean / 95th-percentile inference latency (s) | n/a | 1.57 / 3.22 |
| LLM fallbacks | 0 | 1 |

These are single-run measurements on the current machine, not statistical
performance claims. Repeated trials should be used for a paper's final timing
confidence intervals.

## Authority-layer observations

The run demonstrates three distinct layers of authority:

1. The LLM proposed a high-level mode and power value.
2. The Python runner applied deterministic policy and safety constraints before
   transmitting a UDP command.
3. The Simulink state machine made the final state and power decision from live
   electrical conditions.

From 10--40 s, the LLM requested `CHARGE` at -100 W and the local state machine
accepted it. The LLM case therefore charged for less time than the deterministic
case, which charged from time zero.

At 50 s, the LLM proposed `DISCHARGE` at 250 W. Because SOC was below its target
and the Python guard did not yet classify the 500 W load as an allowed low-SOC
source-deficit event, the transmitted command was `HOLD`. Simulink nevertheless
entered `BUS_SUPPORT` immediately and supplied approximately 25 W because its
local source-reserve rule allows only 475 W from the 500 W source. The same
separation persisted from 60--90 s.

At 100 s, the 600 W load created a clear source deficit. The guarded 100 W
`DISCHARGE` command was accepted, while the local state machine raised the
actual reference to 125 W to preserve its 25 W source reserve. This is an
important result: the AI request is neither blindly followed nor simply
ignored; it is interpreted inside deterministic operating and safety logic.

At 110 s, the local model returned an empty/malformed response. The runner
recorded one fallback and substituted its deterministic policy. Bus support
continued without interruption or a safety stop.

## Interpretation

For this scenario, adding the LLM did not improve the essential fast control
behavior; the local state machine already handled both load transitions. The
LLM implementation instead demonstrates supervisory flexibility, explicit
guarding, failure recovery, and auditable separation of time scales. That is a
stronger research claim than saying an LLM directly controlled a battery.
