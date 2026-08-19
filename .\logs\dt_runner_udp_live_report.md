# Autonomous DT Mission Report

## Mission outcome

- Status: `timed_out`
- Reason: maximum simulation time reached before success criteria
- Supervisor decisions: 21
- Simulated time: 36.203 s to 120.500 s
- SOC: 15.000% -> 15.000%
- Bus voltage: 400.000 V -> 333.333 V

## Goal

- SOC target band: 40.000% to 80.000%
- SOC hard limits: 10.000% to 95.000%
- Bus nominal: 400.000 V
- Bus soft band: 380.000 V to 420.000 V
- Bus hard band: 320.000 V to 480.000 V

## Telemetry summary

- SOC min/max: 15.000% / 15.000%
- Bus voltage min/max: 333.333 V / 400.000 V
- Battery power min/max: 0.000 W / 0.000 W
- Raw load power min/max: -508.567 W / -200.000 W
- Load consumption min/max: 200.000 W / 508.567 W
- Source power min/max: 200.000 W / 500.000 W
- Source deficit min/max: 0.000 W / 8.567 W
- Bus support target min/max: 0.000 W / 333.333 W
- Bus support integral contribution min/max: 0.000 W / 0.000 W
- Bus support trim contribution min/max: 0.000 W / 0.000 W
- Safe discharge cap min/max: 175.000 W / 475.000 W
- Safe charge cap min/max: 0.000 W / 275.000 W
- Recent bus voltage ripple (last 30 s): 333.333 V / 400.000 V (p2p 66.667 V)
- Recent battery power ripple (last 30 s): 0.000 W / 0.000 W (p2p 0.000 W)

## Decision summary

- Policy/LLM requested battery power min/max: -100.000 W / 480.000 W
- Applied battery power min/max: -100.000 W / 333.333 W
- Policy/LLM mode counts:
  - CHARGE: 4
  - DISCHARGE: 11
  - HOLD: 6
- Applied mode counts:
  - CHARGE: 4
  - DISCHARGE: 5
  - HOLD: 12

## Constraint violations

- t=36.203 s: SOC 15.00% below target minimum 40.00%
- t=40.661 s: SOC 15.00% below target minimum 40.00%
- t=44.545 s: SOC 15.00% below target minimum 40.00%
- t=48.501 s: SOC 15.00% below target minimum 40.00%
- t=52.208 s: SOC 15.00% below target minimum 40.00%
- t=56.247 s: SOC 15.00% below target minimum 40.00%
- t=59.819 s: SOC 15.00% below target minimum 40.00%
- t=63.431 s: SOC 15.00% below target minimum 40.00%
- t=67.169 s: SOC 15.00% below target minimum 40.00%
- t=70.688 s: SOC 15.00% below target minimum 40.00%
- t=74.384 s: SOC 15.00% below target minimum 40.00%
- t=78.040 s: SOC 15.00% below target minimum 40.00%
- t=81.661 s: SOC 15.00% below target minimum 40.00%
- t=85.236 s: SOC 15.00% below target minimum 40.00%
- t=88.916 s: SOC 15.00% below target minimum 40.00%
- t=97.789 s: SOC 15.00% below target minimum 40.00%
- t=102.932 s: SOC 15.00% below target minimum 40.00%
- t=102.932 s: bus voltage 339.04 V below soft minimum 380.00 V
- t=107.016 s: SOC 15.00% below target minimum 40.00%
- t=107.016 s: bus voltage 333.48 V below soft minimum 380.00 V
- t=111.013 s: SOC 15.00% below target minimum 40.00%
- t=111.013 s: bus voltage 333.34 V below soft minimum 380.00 V
- t=114.920 s: SOC 15.00% below target minimum 40.00%
- t=114.920 s: bus voltage 333.33 V below soft minimum 380.00 V
- t=118.782 s: SOC 15.00% below target minimum 40.00%
- t=118.782 s: bus voltage 333.33 V below soft minimum 380.00 V

## Decision timeline

| t (s) | SOC (%) | Vbus (V) | P_batt (W) | P_load raw (W) | Load consumed (W) | P_source (W) | Source deficit (W) | Source slack (W) | Bus error (V) | Bus support | Bus I (W) | Bus trim (W) | Raw target (W) | Bus target (W) | Source support | Source target (W) | Max safe discharge (W) | Max safe charge (W) | Faults | Policy/LLM Mode | Policy/LLM P_batt_cmd (W) | Applied Mode | Applied P_batt_cmd (W) | Python adjustment | Policy/LLM reason |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---:|---:|---:|---|---|---:|---|---:|---|---|
| 36.203 | 15.000 | 400.000 | 0.000 | -200.000 | 200.000 | 200.000 | 0.000 | 300.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 175.000 | 275.000 |  | CHARGE | -100.000 | CHARGE | -100.000 | none | LLM: SOC below target and source has charging headroom |
| 40.661 | 15.000 | 400.000 | 0.000 | -200.000 | 200.000 | 200.000 | 0.000 | 300.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 175.000 | 275.000 |  | CHARGE | -100.000 | CHARGE | -100.000 | none | LLM: SOC below target and source has charging headroom |
| 44.545 | 15.000 | 400.000 | 0.000 | -200.000 | 200.000 | 200.000 | 0.000 | 300.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 175.000 | 275.000 |  | CHARGE | -100.000 | CHARGE | -100.000 | none | LLM: SOC below target and source has charging headroom |
| 48.501 | 15.000 | 400.000 | 0.000 | -200.000 | 200.000 | 200.000 | 0.000 | 300.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 175.000 | 275.000 |  | CHARGE | -100.000 | CHARGE | -100.000 | none | LLM: SOC below target and source has charging headroom |
| 52.208 | 15.000 | 399.175 | 0.000 | -498.968 | 498.968 | 500.000 | 0.000 | 0.000 | 0.825 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 473.968 | 0.000 |  | DISCHARGE | 480.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.00% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 56.247 | 15.000 | 399.934 | 0.000 | -499.918 | 499.918 | 500.000 | 0.000 | 0.000 | 0.066 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 474.918 | 0.000 |  | DISCHARGE | 480.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.00% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 59.819 | 15.000 | 399.993 | 0.000 | -499.991 | 499.991 | 500.000 | 0.000 | 0.000 | 0.007 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 474.991 | 0.000 |  | DISCHARGE | 480.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.00% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 63.431 | 15.000 | 399.999 | 0.000 | -499.999 | 499.999 | 500.000 | 0.000 | 0.000 | 0.001 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 474.999 | 0.000 |  | DISCHARGE | 100.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.00% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 67.169 | 15.000 | 400.000 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | DISCHARGE | 100.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.00% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 70.688 | 15.000 | 400.000 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | LLM: SOC and Vbus are inside their target bands and source_overload_w=0 |
| 74.384 | 15.000 | 400.000 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | LLM: SOC and Vbus are inside their target bands and source_overload_w=0 |
| 78.040 | 15.000 | 400.000 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | LLM: SOC and Vbus are inside their target bands and source_overload_w=0 |
| 81.661 | 15.000 | 400.000 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | LLM: SOC and Vbus are inside their target bands and source_overload_w=0 |
| 85.236 | 15.000 | 400.000 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | LLM: SOC and Vbus are inside their target bands and source_overload_w=0 |
| 88.916 | 15.000 | 400.000 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | DISCHARGE | 100.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.00% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 97.789 | 15.000 | 400.000 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | LLM: SOC and Vbus are inside their target bands and source_overload_w=0 |
| 102.932 | 15.000 | 339.045 | 0.000 | -508.567 | 508.567 | 500.000 | 8.567 | 0.000 | 60.955 | active | 0.000 | 0.000 | 313.343 | 313.343 | active | 8.567 | 475.000 | 0.000 |  | DISCHARGE | 313.343 | DISCHARGE | 100.000 | rate limit moved command toward 313.343 W; applied 100.000 W this tick | LLM: bus below target; battery supports bus |
| 107.016 | 15.000 | 333.480 | 0.000 | -500.220 | 500.220 | 500.000 | 0.220 | 0.000 | 66.520 | active | 0.000 | 0.000 | 332.821 | 332.821 | active | 0.220 | 475.000 | 0.000 |  | DISCHARGE | 332.821 | DISCHARGE | 200.000 | rate limit moved command toward 332.821 W; applied 200.000 W this tick | LLM: bus below target; battery supports bus |
| 111.013 | 15.000 | 333.337 | 0.000 | -500.006 | 500.006 | 500.000 | 0.006 | 0.000 | 66.663 | active | 0.000 | 0.000 | 333.319 | 333.319 | active | 0.006 | 475.000 | 0.000 |  | DISCHARGE | 333.319 | DISCHARGE | 300.000 | rate limit moved command toward 333.319 W; applied 300.000 W this tick | LLM: bus below target; battery supports bus |
| 114.920 | 15.000 | 333.333 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 66.667 | active | 0.000 | 0.000 | 333.333 | 333.333 | active | 0.000 | 475.000 | 0.000 |  | DISCHARGE | 333.333 | DISCHARGE | 333.333 | none | LLM: bus below target; battery supports bus |
| 118.782 | 15.000 | 333.333 | 0.000 | -500.000 | 500.000 | 500.000 | 0.000 | 0.000 | 66.667 | active | 0.000 | 0.000 | 333.333 | 333.333 | active | 0.000 | 475.000 | 0.000 |  | DISCHARGE | 333.333 | DISCHARGE | 333.333 | none | LLM: bus below target; battery supports bus |
