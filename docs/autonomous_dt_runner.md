# Autonomous DT runner

This branch adds the first source-code scaffold for the autonomous-control
variant of the digital-twin project.

The runner treats Simulink as an environment with a compact
observation/supervisory-intent contract. The UDP command is not the converter
reference; it is an input to the deterministic local state controller:

```text
observe -> LLM request -> Python guard -> UDP intent
        -> 1 ms Simulink state controller -> converter/plant
```

For the battery/load-bus model, the initial contract is:

```text
Observation:
    sim_time_s
    soc_pct
    v_bus_v
    v_batt_v
    i_batt_a
    p_batt_w
    p_load_w
    load_consumption_w
    p_source_w
    max_safe_discharge_w
    max_safe_charge_w
    source_power_limit_w
    source_can_sink_power
    source_at_limit
    source_available
    fault_flags

Supervisory intent:
    mode: CHARGE | HOLD | DISCHARGE | SAFE
    p_batt_cmd_w
    enable
    reason
```

The guarded state-machine model uses four local states that remain independent
of LLM timing: `HOLD` (0), `CHARGE` (1), `BUS_SUPPORT` (2), and `SAFE_LOCAL`
(3). It reports `state_code` in observation `extra` telemetry. Positive final
battery power discharges into the bus; negative power charges the battery.

The current implementation includes:

- `AutonomousRunner`: periodic supervisory loop.
- `SocBandPolicy`: first deterministic policy for maintaining SOC and bus
  voltage constraints.
- `LLMControlPolicy`: OpenAI-compatible AI policy that proposes bounded
  supervisory commands as JSON.
- `CommandConstraintLayer`: deterministic guard layer for source headroom,
  bus-voltage anti-chatter, command clipping, and rate limiting.
- `DT_enviroment_state_machine_llm_udp.slx`: guarded UDP model where the local
  state machine owns the final state and battery-power reference.
- `MockBatteryBusBackend`: test backend so the runner is executable before the
  Simulink bridge is wired.
- `SimulinkBackend`: MATLAB Engine bridge for running the Simulink model in
  supervisor-sized chunks.

Run the mock mission:

```powershell
..\AI_work\.venv\Scripts\python.exe .\run_dt_runner.py --backend mock
```

Run the mock mission with the AI policy:

```powershell
..\AI_work\.venv\Scripts\python.exe .\run_dt_runner.py --backend mock --policy llm --llm-base-url http://localhost:1234/v1 --llm-model llama-3-groq-8b-tool-use
```

In this mode the model decides only:

```json
{
  "mode": "CHARGE | HOLD | DISCHARGE | SAFE",
  "p_batt_cmd_w": -100.0,
  "reason": "short explanation"
}
```

The runner still enforces hard stops, command clipping, rate limits, and
physical request guards. Positive `p_batt_cmd_w` requests battery discharge;
negative requests charging. In the guarded UDP model, Simulink can override
either request based on live bus voltage, source reserve, SOC, command validity,
and the state-transition hysteresis.

For the current battery/load-bus plant, the source is treated as a one-quadrant
device by default: it can supply power, but it cannot safely absorb reverse
power. The runner therefore derives `load_consumption_w` from the raw signed
`p_load_w` signal and computes `max_safe_discharge_w`. LLM and heuristic
commands are clipped to that discharge cap before they reach Simulink. The
runner also computes `max_safe_charge_w` when source-limit telemetry or
configuration is available. That calculation is made in Python from source
limit minus load consumption minus margin, so battery discharge cannot create
fake charging headroom. Charge requests are blocked at zero headroom, derated
to available headroom, and held off briefly after a low-bus, no-headroom, or
bus-support discharge event so the controller does not chatter at the source limit. The
runner also blocks discretionary discharge below the target SOC minimum unless
the bus is below the soft voltage minimum.

Useful guard knobs:

```powershell
--source-min-power 0 `
--source-power-margin 25 `
--source-power-limit 3000 `
--charge-power-margin 25 `
--charge-bus-hysteresis-volts 5 `
--charge-recovery-hold-seconds 10 `
--post-discharge-charge-hold-seconds 10 `
--allow-source-backfeed `
--allow-charge-without-source-headroom `
--allow-discharge-below-soc-min
```

The `--allow-*` flags disable guards and should usually be left off for the
simple power-limited source model.

Write a decision log:

```powershell
..\AI_work\.venv\Scripts\python.exe .\run_dt_runner.py --backend mock --csv .\logs\dt_runner_mock.csv
```

Write a Markdown mission report:

```powershell
..\AI_work\.venv\Scripts\python.exe .\run_dt_runner.py --backend mock --report .\logs\dt_runner_report.md
```

Run with the OpenAI-compatible LLM policy and write a local JSONL trace of every
LLM request, response, or fallback:

```powershell
..\AI_work\.venv\Scripts\python.exe .\run_dt_runner.py `
  --backend simulink `
  --policy llm `
  --llm-base-url http://localhost:1234/v1 `
  --llm-model llama-3-groq-8b-tool-use `
  --llm-api-key lm-studio `
  --llm-verbose `
  --llm-max-tokens 120 `
  --llm-command-limit 500 `
  --llm-log .\logs\dt_runner_ai_30s_llm.jsonl `
  --model-path .\Modules\Digital_Twins\DT_enviroment.slx `
  --tick-seconds 1 `
  --startup-grace-seconds 1 `
  --max-sim-seconds 30 `
  --success-hold-seconds 999 `
  --bus-nominal 400 `
  --max-p-batt 500 `
  --max-p-batt-step 100 `
  --source-power-margin 25 `
  --charge-power-margin 25 `
  --charge-recovery-hold-seconds 10 `
  --post-discharge-charge-hold-seconds 10 `
  --csv .\logs\dt_runner_ai_30s.csv `
  --report .\logs\dt_runner_ai_30s_report.md
```

For small local models, leave `--llm-strict` off while tuning. If the model
echoes the prompt or returns malformed JSON, the runner will reject that
response and fall back to the deterministic SOC/bus policy. Add `--llm-strict`
only when you want malformed LLM output to fail the mission immediately.

By default, `--policy llm` is research mode: the LLM's high-level mode choice is
used directly after JSON validation, while the runner still owns hard stops,
rate limits, and physical command clipping. If you want a safer demo mode where
the deterministic SOC/bus policy can veto an obviously wrong LLM mode, add
`--llm-mode-gate`.

The LLM prompt includes derived decision booleans such as `normal_hold`,
`charge_needed`, and `bus_support_needed`. These are not actuator commands; they
are compact state features that help small local models choose the right mode
without falling back to the deterministic policy.

Next Simulink wiring step:

1. Create/log one `dt_state` bus in the model.
2. Add one command input path that reads the workspace variables
   `P_batt_cmd`, `enable_cmd`, and optionally `mode_cmd`.
   The bridge writes `mode_cmd` as a numeric code:

   ```text
   CHARGE = -1
   HOLD = 0
   DISCHARGE = 1
   SAFE = 99
   ```
3. Map `P_batt_cmd` through your battery power controller:

   ```text
   P_batt_error = P_batt_cmd - P_batt_measured
   PI(P_batt_error) -> voltage/duty correction
   D_cmd = saturate(controller output)
   ```

   The agent should not command duty directly. Simulink owns the inner
   `P_cmd -> PI -> D` control loop.

4. Add safety saturation/rate limiting inside Simulink too.
5. Run the Simulink backend:

   ```powershell
   ..\AI_work\.venv\Scripts\python.exe .\run_dt_runner.py --backend simulink --tick-seconds 5 --max-sim-seconds 60
   ```

The MATLAB helper files live in `Modules/Digital_Twins/matlab_bridge/`.
They return observations to Python as JSON, which avoids fragile MATLAB struct
conversion rules in the Python engine.

## Live Simulink UDP mode

The UDP backend keeps Simulink running continuously while Python exchanges
supervisory packets. The local controller remains active between LLM decisions.

```text
Simulink -> observation + reported local state -> Python runner
Python runner -> LLM request -> Python guard -> UDP supervisory intent
UDP receiver -> validity/staleness boundary -> local state controller
Local state controller -> final P_batt_ref -> converter/plant
```

The GUI launches the runner with `--emit-gui-events`. Those compact console
events drive a generic live control-path display without changing the UDP
packet contract. The GUI can show runner-provided summaries for other digital
twins; this battery runner supplies request, guarded intent, local state, and
measured-power summaries. Because an observation is received before the next
supervisory intent is sent, the local state and feedback are the latest values
*reported by Simulink*.

Default packet endpoints:

```text
Python -> Simulink commands:      127.0.0.1:55000
Simulink -> Python observations:  127.0.0.1:55001
Optional monitor republish:       127.0.0.1:55002
```

The packet schema is compact JSON in one UDP datagram:

```json
{
  "protocol": "dt_udp",
  "version": 1,
  "kind": "command | observation | control | ack",
  "seq": 1,
  "sent_at_epoch_s": 1780000000.0,
  "command": {
    "mode": "CHARGE | HOLD | DISCHARGE | SAFE",
    "mode_code": -1.0,
    "p_batt_cmd_w": -100.0,
    "enable": true,
    "reason": "short explanation"
  }
}
```

Observation packets use the same outer fields and include:

```json
{
  "observation": {
    "sim_time_s": 12.5,
    "soc_pct": 55.0,
    "v_bus_v": 400.0,
    "v_batt_v": 303.0,
    "i_batt_a": 0.0,
    "p_batt_w": 0.0,
    "p_load_w": 2500.0,
    "load_consumption_w": 2500.0,
    "p_source_w": 2500.0,
    "max_safe_discharge_w": 2475.0,
    "max_safe_charge_w": 475.0,
    "source_power_limit_w": 3000.0,
    "source_can_sink_power": false,
    "source_at_limit": false,
    "source_available": true,
    "fault_flags": {},
    "extra": {}
  }
}
```

### Simulink block wiring

The UDP System-object helpers live in `Modules/Digital_Twins/matlab_udp/`.
Add that folder to the MATLAB path before opening the model:

```matlab
addpath("Modules/Digital_Twins/matlab_udp")
```

Add a MATLAB System block using `DTUdpCommandReceiver` and wire the outputs:

```text
p_batt_cmd_w  -> battery power controller command input
enable_cmd    -> supervisory enable gate
mode_code     -> optional mode selector / diagnostics
command_seq   -> optional diagnostics
command_age_s -> optional stale-command safety logic
```

The receiver maps modes to numeric codes:

```text
CHARGE = -1
HOLD = 0
DISCHARGE = 1
SAFE = 99
```

The receiver has a `MaxCommandAgeS` property. If no fresh command arrives before
that age, it outputs `enable_cmd = false`, `mode_code = 99`, and
`p_batt_cmd_w = 0`. Keep this as a second safety layer inside Simulink.

The UDP System objects use MATLAB's `udpport`, which is not supported for code
generation. The helper classes force MATLAB System block simulation to
`Interpreted execution`. If an existing block still shows `Code generation`,
open the block parameters and set `Simulate using` to `Interpreted execution`,
or refresh/recreate the block after pulling the updated `.m` files. This path is
intended for normal live desktop simulation; generated-code or real-time targets
should use Simulink/DSP UDP blocks instead.

Add a second MATLAB System block using `DTUdpObservationSender` and wire these
inputs:

```text
sim_time_s
soc_pct
v_bus_v
v_batt_v
i_batt_a
p_batt_w
p_load_w
p_source_w
source_at_limit
source_available
```

`p_load_w` may be signed according to your Simulink sensor direction. The Python
runner preserves that raw value, then derives positive `load_consumption_w`
internally. You do not need to add a separate Simulink signal for
`load_consumption_w` unless you want to override the derived value.

If your source has a known fixed limit, set the sender block's
`SourcePowerLimitW` property or pass `--source-power-limit` to the Python
runner. That gives the deterministic charge guard enough information to avoid
charge/start-stop chatter when load sits near the power-supply limit. Python
still computes the enforced charge limit itself from source limit and load.

For `sim_time_s`, a Clock block is sufficient. Set the sender `RemoteHost` and
`RemotePort` to the Python runner's observation listener. The default is
`127.0.0.1:55001`.

### Running the UDP supervisor

Start the Simulink model first so it is already sending observations. Then run:

```powershell
..\AI_work\.venv\Scripts\python.exe .\run_dt_runner.py `
  --backend udp `
  --policy llm `
  --llm-base-url http://localhost:1234/v1 `
  --llm-model llama-3-groq-8b-tool-use `
  --llm-max-tokens 120 `
  --llm-command-limit 500 `
  --tick-seconds 1 `
  --max-sim-seconds 60 `
  --success-hold-seconds 999 `
  --source-power-margin 25 `
  --charge-power-margin 25 `
  --charge-recovery-hold-seconds 10 `
  --post-discharge-charge-hold-seconds 10 `
  --udp-command-host 127.0.0.1 `
  --udp-command-port 55000 `
  --udp-observation-port 55001 `
  --udp-command-resend-period 0.25 `
  --udp-republish-host 127.0.0.1 `
  --udp-republish-port 55002 `
  --csv .\logs\dt_runner_udp_live.csv `
  --report .\logs\dt_runner_udp_live_report.md
```

In UDP mode, `advance()` waits for live observation packets instead of calling
MATLAB Engine. The simulation clock comes from Simulink, so the model should use
simulation pacing or a real-time target if you want wall-clock viewing.

To watch republished observations in a second terminal:

```powershell
..\AI_work\.venv\Scripts\python.exe .\run_dt_udp_monitor.py --port 55002
```

To test the Simulink command receiver without the full runner, start the model
and run:

```powershell
..\AI_work\.venv\Scripts\python.exe .\run_dt_udp_send_command.py `
  --mode DISCHARGE `
  --power 100 `
  --count 20 `
  --interval 0.25
```

If the receiver is getting packets, the `command_seq` output should increment
and `command_age_s` should reset near zero on each received packet. If those do
not move, check that the receiver `LocalPort` is `55000`, the block is using
`Interpreted execution`, and no stale MATLAB `udpport` object is already bound
to that port. Run `clear classes` after stopping the model to release old System
object instances.
