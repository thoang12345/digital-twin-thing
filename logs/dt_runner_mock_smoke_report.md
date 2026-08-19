# Autonomous DT Mission Report

## Mission outcome

- Status: `timed_out`
- Reason: maximum simulation time reached before success criteria
- Supervisor decisions: 5
- Simulated time: 0.000 s to 5.000 s
- SOC: 55.000% -> 55.000%
- Bus voltage: 400.000 V -> 400.000 V

## Goal

- SOC target band: 40.000% to 80.000%
- SOC hard limits: 10.000% to 95.000%
- Bus nominal: 400.000 V
- Bus soft band: 380.000 V to 420.000 V
- Bus hard band: 320.000 V to 480.000 V

## Telemetry summary

- SOC min/max: 55.000% / 55.000%
- Bus voltage min/max: 400.000 V / 400.000 V
- Battery power min/max: 0.000 W / 0.000 W
- Raw load power min/max: 2500.000 W / 2500.000 W
- Load consumption min/max: 2500.000 W / 2500.000 W
- Source power min/max: 2500.000 W / 2500.000 W
- Source deficit min/max: 0.000 W / 0.000 W
- Bus support target min/max: 0.000 W / 0.000 W
- Bus support integral contribution min/max: 0.000 W / 0.000 W
- Bus support trim contribution min/max: 0.000 W / 0.000 W
- Safe discharge cap min/max: 500.000 W / 500.000 W
- Safe charge cap min/max: 475.000 W / 475.000 W
- Recent bus voltage ripple (last 30 s): 400.000 V / 400.000 V (p2p 0.000 V)
- Recent battery power ripple (last 30 s): 0.000 W / 0.000 W (p2p 0.000 W)

## Decision summary

- Policy/LLM requested battery power min/max: 0.000 W / 0.000 W
- Applied battery power min/max: 0.000 W / 0.000 W
- Policy/LLM mode counts:
  - HOLD: 5
- Applied mode counts:
  - HOLD: 5

## Constraint violations

- No soft or hard constraint violations were recorded.

## Decision timeline

| t (s) | SOC (%) | Vbus (V) | P_batt (W) | P_load raw (W) | Load consumed (W) | P_source (W) | Source deficit (W) | Source slack (W) | Bus error (V) | Bus support | Bus I (W) | Bus trim (W) | Raw target (W) | Bus target (W) | Source support | Source target (W) | Max safe discharge (W) | Max safe charge (W) | Faults | Policy/LLM Mode | Policy/LLM P_batt_cmd (W) | Applied Mode | Applied P_batt_cmd (W) | Python adjustment | Policy/LLM reason |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---:|---:|---:|---|---|---:|---|---:|---|---|
| 0.000 | 55.000 | 400.000 | 0.000 | 2500.000 | 2500.000 | 2500.000 | 0.000 | 500.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 500.000 | 475.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | SOC and bus voltage are inside target band |
| 1.000 | 55.000 | 400.000 | 0.000 | 2500.000 | 2500.000 | 2500.000 | 0.000 | 500.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 500.000 | 475.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | SOC and bus voltage are inside target band |
| 2.000 | 55.000 | 400.000 | 0.000 | 2500.000 | 2500.000 | 2500.000 | 0.000 | 500.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 500.000 | 475.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | SOC and bus voltage are inside target band |
| 3.000 | 55.000 | 400.000 | 0.000 | 2500.000 | 2500.000 | 2500.000 | 0.000 | 500.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 500.000 | 475.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | SOC and bus voltage are inside target band |
| 4.000 | 55.000 | 400.000 | 0.000 | 2500.000 | 2500.000 | 2500.000 | 0.000 | 500.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 500.000 | 475.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | SOC and bus voltage are inside target band |
