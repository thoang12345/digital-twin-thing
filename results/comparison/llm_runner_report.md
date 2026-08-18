# Autonomous DT Mission Report

## Mission outcome

- Status: `timed_out`
- Reason: maximum simulation time reached before success criteria
- Supervisor decisions: 12
- Simulated time: 0.000 s to 120.000 s
- SOC: 15.000% -> 15.000%
- Bus voltage: 400.000 V -> 400.000 V

## Goal

- SOC target band: 40.000% to 80.000%
- SOC hard limits: 10.000% to 95.000%
- Bus nominal: 400.000 V
- Bus soft band: 380.000 V to 420.000 V
- Bus hard band: 320.000 V to 480.000 V

## Telemetry summary

- SOC min/max: 15.000% / 15.007%
- Bus voltage min/max: 400.000 V / 400.000 V
- Battery power min/max: -100.000 W / 125.000 W
- Raw load power min/max: -600.000 W / -200.000 W
- Load consumption min/max: 200.000 W / 600.000 W
- Source power min/max: 0.000 W / 481.250 W
- Source deficit min/max: 0.000 W / 100.000 W
- Bus support target min/max: 0.000 W / 100.000 W
- Bus support integral contribution min/max: 0.000 W / 0.000 W
- Bus support trim contribution min/max: 0.000 W / 0.000 W
- Safe discharge cap min/max: 0.000 W / 480.000 W
- Safe charge cap min/max: 0.000 W / 275.000 W
- Recent bus voltage ripple (last 30 s): 400.000 V / 400.000 V (p2p 0.000 V)
- Recent battery power ripple (last 30 s): 25.000 W / 125.000 W (p2p 100.000 W)

## Decision summary

- Policy/LLM requested battery power min/max: -100.000 W / 250.000 W
- Applied battery power min/max: -100.000 W / 100.000 W
- Policy/LLM mode counts:
  - CHARGE: 4
  - DISCHARGE: 7
  - HOLD: 1
- Applied mode counts:
  - CHARGE: 4
  - DISCHARGE: 2
  - HOLD: 6

## Constraint violations

- t=0.000 s: SOC 15.00% below target minimum 40.00%
- t=10.000 s: SOC 15.00% below target minimum 40.00%
- t=20.000 s: SOC 15.00% below target minimum 40.00%
- t=30.000 s: SOC 15.00% below target minimum 40.00%
- t=40.000 s: SOC 15.01% below target minimum 40.00%
- t=50.000 s: SOC 15.01% below target minimum 40.00%
- t=60.000 s: SOC 15.01% below target minimum 40.00%
- t=70.000 s: SOC 15.01% below target minimum 40.00%
- t=80.000 s: SOC 15.01% below target minimum 40.00%
- t=90.000 s: SOC 15.01% below target minimum 40.00%
- t=100.000 s: SOC 15.00% below target minimum 40.00%
- t=110.000 s: SOC 15.00% below target minimum 40.00%

## Decision timeline

| t (s) | SOC (%) | Vbus (V) | P_batt (W) | P_load raw (W) | Load consumed (W) | P_source (W) | Source deficit (W) | Source slack (W) | Bus error (V) | Bus support | Bus I (W) | Bus trim (W) | Raw target (W) | Bus target (W) | Source support | Source target (W) | Max safe discharge (W) | Max safe charge (W) | Faults | Policy/LLM Mode | Policy/LLM P_batt_cmd (W) | Applied Mode | Applied P_batt_cmd (W) | Python adjustment | Policy/LLM reason |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---:|---:|---:|---|---|---:|---|---:|---|---|
| 0.000 | 15.000 | 400.000 | 0.000 | -200.000 | 200.000 | 0.000 | 0.000 | 500.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 0.000 | 275.000 |  | HOLD | 0.000 | HOLD | 0.000 | none | startup grace period; holding battery command while model settles |
| 10.000 | 15.000 | 400.000 | 0.000 | -200.000 | 200.000 | 200.000 | 0.000 | 300.000 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 175.000 | 275.000 |  | CHARGE | -100.000 | CHARGE | -100.000 | none | LLM: SOC below target and source has charging headroom |
| 20.000 | 15.001 | 400.000 | -100.000 | -200.000 | 200.000 | 305.263 | 0.000 | 194.737 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 175.000 | 275.000 |  | CHARGE | -100.000 | CHARGE | -100.000 | none | LLM: SOC below target and source has charging headroom |
| 30.000 | 15.003 | 400.000 | -100.000 | -200.000 | 200.000 | 305.263 | 0.000 | 194.737 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 175.000 | 275.000 |  | CHARGE | -100.000 | CHARGE | -100.000 | none | LLM: SOC below target and source has charging headroom |
| 40.000 | 15.005 | 400.000 | -100.000 | -200.000 | 200.000 | 305.263 | 0.000 | 194.737 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 175.000 | 275.000 |  | CHARGE | -100.000 | CHARGE | -100.000 | none | LLM: SOC below target and source has charging headroom |
| 50.000 | 15.007 | 400.000 | -100.000 | -500.000 | 500.000 | 305.263 | 0.000 | 194.737 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 280.263 | 0.000 |  | DISCHARGE | 250.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.01% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 60.000 | 15.007 | 400.000 | 25.000 | -500.000 | 500.000 | 476.250 | 0.000 | 23.750 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | DISCHARGE | 100.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.01% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 70.000 | 15.006 | 400.000 | 25.000 | -500.000 | 500.000 | 476.250 | 0.000 | 23.750 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | DISCHARGE | 100.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.01% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 80.000 | 15.006 | 400.000 | 25.000 | -500.000 | 500.000 | 476.250 | 0.000 | 23.750 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | DISCHARGE | 100.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.01% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 90.000 | 15.005 | 400.000 | 25.000 | -500.000 | 500.000 | 476.250 | 0.000 | 23.750 | 0.000 | - | 0.000 | 0.000 | 0.000 | 0.000 | - | 0.000 | 475.000 | 0.000 |  | DISCHARGE | 100.000 | HOLD | 0.000 | blocked discharge because SOC is below the target minimum (15.01% <= 40.00%) and neither bus voltage nor source overload requires support | LLM: SOC below soc_min and source has headroom |
| 100.000 | 15.005 | 400.000 | 25.000 | -600.000 | 600.000 | 476.250 | 100.000 | 23.750 | 0.000 | - | 0.000 | 0.000 | 100.000 | 100.000 | active | 100.000 | 476.250 | 0.000 |  | DISCHARGE | 100.000 | DISCHARGE | 100.000 | none | LLM: bus below target; battery supports bus |
| 110.000 | 15.002 | 400.000 | 125.000 | -600.000 | 600.000 | 481.250 | 100.000 | 18.750 | 0.000 | active | 0.000 | 0.000 | 100.000 | 100.000 | active | 100.000 | 480.000 | 0.000 |  | DISCHARGE | 100.000 | DISCHARGE | 100.000 | none | LLM policy fallback: JSONDecodeError: Expecting value: line 1 column 1 (char 0); source is overloaded relative to load demand; preemptively support load bus |
