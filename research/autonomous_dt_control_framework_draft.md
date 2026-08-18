# A Modular Framework for Guarded Autonomous Digital Twin Supervisory Control

_Draft for IEEE special-call submission._

Author note: replace the title, author block, target venue, and reference placeholders after the exact IEEE special call is recovered. This draft is intentionally framed as a framework paper. The case study supports the framework, but the primary contribution is the reusable architecture.

## Abstract

Digital twins are increasingly used to represent, monitor, and evaluate complex engineered systems, yet many digital twin deployments remain advisory rather than autonomous. Moving from passive digital twin visualization toward autonomous digital twin control requires more than connecting an artificial intelligence model to a simulator. A practical autonomous digital twin controller must define a stable state-action contract, separate high-level supervisory decisions from low-level plant control, enforce safety constraints outside the policy model, support multiple runtime backends, and produce an auditable record of each decision. This paper proposes a modular framework for guarded autonomous digital twin supervisory control. The framework treats the digital twin as an environment exposed through a compact observation interface and a bounded command interface. A supervisory runner coordinates observation, policy selection, command limiting, backend execution, safety checking, and mission reporting. Control policies are interchangeable and may include deterministic rule-based policies, learned policies, or large-language-model-based decision policies, while an independent guard layer enforces hard constraints, soft-constraint reporting, command clipping, rate limiting, and fallback behavior. The framework is demonstrated through a battery-assisted DC load-bus digital twin with MATLAB/Simulink and UDP runtime interfaces. The case study illustrates how the proposed architecture supports mock testing, live digital twin communication, policy substitution, and transparent decision logging. The result is a reusable design pattern for developing autonomous digital twin controllers that are inspectable, extensible, and constrained by explicit operational safety contracts.

## Keywords

Digital twin; autonomous control; supervisory control; guarded autonomy; large language models; Simulink; microgrids; DC power systems; safety constraints; decision logging.

## I. Introduction

Digital twins have become an important tool for representing physical systems, integrating simulation models with operational data, and supporting engineering decision-making. In power and energy systems, manufacturing, transportation, and cyber-physical infrastructure, digital twins can provide a computational view of the asset state, forecast future behavior, and evaluate hypothetical interventions before they are applied to a real system. Despite this promise, many digital twin systems remain passive. They visualize state, answer questions, or provide offline analysis, but they do not participate directly in closed-loop or supervisory control.

Autonomous digital twin control is a natural next step, but it also creates a more difficult systems problem. A digital twin controller must interact with a model or live simulation, interpret state estimates, select actions, and apply those actions through a communication pathway. If artificial intelligence is used as part of the decision process, the architecture must also define what the AI is allowed to decide, how its outputs are validated, and how the system responds when the AI output is unsafe, malformed, delayed, or unavailable. In practical engineering environments, the controller must also remain auditable. Operators and researchers should be able to inspect what the digital twin observed, what command was issued, why the command was selected, which constraints were active, and whether the mission succeeded or failed.

These requirements suggest that autonomous digital twin control should not be treated as a direct connection between an AI model and a plant model. Instead, it should be treated as a guarded supervisory-control framework. The digital twin provides a structured observation. A policy proposes a bounded high-level command. A guard layer validates and limits the command. A backend adapter applies the command to a simulation, live model, or physical interface. A reporting layer records the complete decision trace. This architecture allows autonomy to be introduced incrementally while preserving clear responsibility boundaries between the policy, the digital twin, the safety logic, and the plant-level controllers.

This paper proposes such a framework. The framework is designed for autonomous digital twin supervisory control, where the autonomous agent is responsible for high-level operating decisions rather than direct low-level control signals. In the motivating case study, a digital twin of a battery-assisted DC load bus exposes state variables such as state of charge, bus voltage, battery power, load power, source power, source availability, and fault flags. The supervisory controller chooses from a bounded command set: charge, hold, discharge, or safe. The inner converter control remains inside the Simulink model, while the autonomous supervisor commands a battery-power reference. This separation is important because it prevents the autonomous policy from issuing raw actuator commands such as duty ratio values.

The proposed framework is intentionally policy-agnostic. A deterministic state-of-charge and bus-voltage policy can be used for baseline behavior. A learned or large-language-model-based policy can be substituted through the same interface. In all cases, the runner owns hard safety stops, command clipping, rate limits, and mission logging. Thus, the framework supports experimentation with advanced policy models without transferring safety responsibility to those models.

The main contributions of this paper are:

1. A modular framework for autonomous digital twin supervisory control based on an explicit observation, goal, command, and backend contract.
2. A guarded execution architecture that separates policy proposals from safety enforcement, command limiting, and mission termination.
3. A policy interface that supports deterministic, learned, or large-language-model-based supervisory decisions without changing the digital twin backend.
4. A backend abstraction that supports mock simulation, MATLAB/Simulink engine execution, and live UDP communication with a running digital twin.
5. A case-study implementation for a battery-assisted DC bus digital twin, including decision traces and mission-report generation for framework evaluation.

The remainder of the paper is organized as follows. Section II motivates the autonomous digital twin supervisory-control problem. Section III defines the framework requirements. Section IV presents the proposed architecture. Section V describes the state-action contract and guarded control loop. Section VI presents the policy layer. Section VII describes the backend layer. Section VIII presents the case-study implementation. Section IX outlines the evaluation protocol. Section X discusses the framework implications. Section XI presents limitations and future work, and Section XII concludes the paper.

## II. Background and Motivation

### A. Digital Twins as Runtime Control Contexts

A digital twin is commonly understood as a digital representation of a physical system that is linked to data, models, or operational context. In many engineering applications, the digital twin supports monitoring, diagnosis, simulation, and forecasting. However, once the digital twin is connected to a control task, its role changes. It is no longer only an information source. It becomes part of a decision loop.

This shift introduces several architectural questions. What information does the twin expose to the controller? Which actions may the controller request? How are constraints represented? Does the digital twin own the plant-level controller, or does the autonomous agent command low-level actuator variables directly? How are decisions logged? How does the system behave when the digital twin communication path fails?

These questions are not solved by model fidelity alone. A high-fidelity digital twin can still be unsafe or difficult to control if its interface to the autonomous supervisor is unstructured. Conversely, a simplified digital twin can be useful for early autonomy research if it exposes a clear state-action contract and supports repeatable testing. The proposed framework focuses on this interface layer.

### B. Supervisory Control Rather Than Direct Actuation

The framework proposed here is designed for supervisory control. In supervisory control, the autonomous digital twin controller selects high-level commands, operating modes, or references, while lower-level control loops remain responsible for fast plant dynamics. For a battery-connected DC bus, the supervisor may request a battery power reference, but it should not directly command the converter duty ratio. The duty ratio, pulse-width modulation, current limiting, and converter dynamics remain inside the plant controller or simulation model.

This separation is particularly important when AI models are involved. A language model or other learned policy may be useful for selecting a mode, interpreting a fault context, or choosing a conservative power request. It should not be responsible for raw switching commands. The framework therefore constrains the policy action space to bounded supervisory commands and delegates fast physical control to the digital twin or embedded control layer.

### C. Need for Guarded Autonomy

Autonomous digital twin control must be guarded because policy outputs can be wrong for many reasons. A deterministic policy may be incomplete. A learned policy may generalize poorly. A language-model policy may return malformed output, propose an unsafe command, or fail to respond. Communication with a live digital twin may be delayed or interrupted. A simulation may produce transient startup values or fault flags.

Guarded autonomy addresses these issues by placing a deterministic safety and validation layer between the policy and the backend. The guard layer can enforce hard limits, convert unsafe conditions into safe-stop commands, clip power references, limit command rate of change, and fall back to a trusted baseline when an AI policy fails. In the proposed framework, the policy proposes, but the runner enforces.

### D. Framework Paper Positioning

This paper is positioned as a framework contribution. The objective is not to claim that a particular controller is globally optimal, nor that an AI policy outperforms classical control across all operating conditions. Instead, the objective is to define and demonstrate an architecture that makes autonomous digital twin supervisory control modular, inspectable, and safe enough for systematic experimentation. The case study is used to illustrate how the framework operates and how future control policies can be evaluated within a common guarded structure.

## III. Framework Requirements

The framework was designed around seven requirements that recur in autonomous digital twin control applications.

### A. Explicit State-Action Contract

The digital twin must expose a compact and typed observation to the autonomous supervisor. The policy should not infer operational variables from unstructured text or arbitrary simulator internals. Similarly, the command interface must restrict the supervisor to meaningful high-level commands. This state-action contract enables validation, testing, logging, and backend substitution.

### B. Policy Substitutability

The framework must support multiple control policies without changing the runner or the digital twin backend. A deterministic policy should be able to serve as a baseline. A learned policy, optimization policy, or language-model policy should be able to use the same observation and return the same command type. This requirement supports ablation studies and reduces coupling between autonomy research and simulation integration.

### C. Safety Ownership Outside the Policy

Safety should not depend solely on the policy. The framework must enforce hard constraints, command bounds, and rate limits outside the policy module. This allows experimental or AI-based policies to be evaluated without granting them direct authority over unsafe actions.

### D. Backend Independence

The autonomous runner should operate over a stable backend interface. The same supervisory loop should work with a mock simulator, a MATLAB/Simulink model controlled through MATLAB Engine, or a continuously running live model using UDP messages. Backend independence improves testability and supports progressive development from offline tests to live digital twin experiments.

### E. Communication Robustness

A practical digital twin controller must tolerate communication details such as stale observations, repeated commands, packet schemas, simulation startup transients, and backend exceptions. These details should be contained in backend adapters rather than distributed across the policy logic.

### F. Auditability

Every supervisory decision should be recorded with the observation, selected command, command reason, status, and active constraint violations. This is required for debugging, scientific evaluation, and operator trust. For AI policies, the system should also support optional request and response traces.

### G. Incremental Autonomy

The framework should support a progression from deterministic policies and mock simulations toward AI policies and live digital twin communication. Incremental autonomy is important because autonomous control research often advances in stages. Early experiments should not require complete live-system integration.

## IV. Proposed Framework

### A. Architecture Overview

The proposed framework consists of six primary components:

1. A digital twin backend that exposes reset, observe, apply-command, advance, and close operations.
2. A structured observation object containing the current digital twin state.
3. A goal object containing target bands, hard limits, mission duration, and success criteria.
4. A policy module that maps an observation and goal to a high-level command.
5. A guarded runner that enforces safety checks, command limits, startup behavior, and mission termination.
6. A reporting layer that writes decision logs and mission summaries.

At each supervisor tick, the runner receives or requests an observation from the backend. It evaluates hard and soft constraints. If a hard constraint is violated, the runner sends a safe command and terminates the mission. If the mission has satisfied its success criteria for the required duration, the runner returns success. Otherwise, the runner calls the active policy, limits the resulting command, applies the command through the backend, records the event, and advances to the next observation.

The high-level control flow is:

```text
initialize backend and goal
observe digital twin state
repeat until success, timeout, safety stop, or failure:
    check hard constraints
    check soft constraints
    if in startup grace period:
        issue hold command
    else:
        request command from policy
    clip and rate-limit command
    apply command to backend
    record decision event
    advance or wait for next observation
write mission report and decision log
```

This structure keeps the policy interface simple while placing mission-level authority in the runner.

### B. Formal Framework Representation

Let the digital twin at supervisory step `k` expose an observation

```text
o_k = O(DT, t_k),
```

where `O` is the backend observation function, `DT` is the digital twin runtime, and `t_k` is the current simulation or wall-clock time. Let the mission goal be

```text
G = {B_soft, B_hard, T_success, T_max},
```

where `B_soft` defines desired operating bands, `B_hard` defines hard safety limits, `T_success` defines the required stable hold time, and `T_max` defines the maximum mission duration.

A policy proposes a command:

```text
u_k^p = pi(o_k, G).
```

The guard layer maps the proposed command to an executable command:

```text
u_k = gamma(u_k^p, o_k, G, u_{k-1}),
```

where `gamma` enforces safety stops, command bounds, rate limits, enable flags, and fallback behavior. The backend then applies the command:

```text
DT_{k+1} = A(DT_k, u_k, Delta t),
```

where `A` is implemented by a simulator, a MATLAB/Simulink bridge, a live UDP interface, or another runtime adapter.

The framework therefore separates policy intelligence from execution authority. The policy selects `u_k^p`; the guard determines whether and how it becomes `u_k`.

### C. Component Interfaces

The backend interface contains five operations:

```text
reset() -> observation
observe() -> observation
apply_command(command) -> None
advance(seconds) -> observation
close() -> None
```

This interface is intentionally small. It is sufficient for mock simulation, step-based simulator integration, and live communication. In live UDP mode, the `advance` operation does not force the simulator to step. Instead, it waits until the live digital twin publishes an observation whose simulation timestamp has advanced sufficiently.

The policy interface contains one operation:

```text
choose_action(observation, goal) -> command
```

This allows a deterministic controller, optimization routine, reinforcement-learning policy, or language-model policy to be substituted without modifying the runner.

## V. State-Action Contract and Guarded Execution

### A. Observation Contract

The case-study implementation uses a compact digital twin observation for a battery-assisted DC bus. The observation fields are shown in Table I.

**Table I. Digital twin observation fields**

| Field | Description |
|---|---|
| `sim_time_s` | Simulation or digital twin time in seconds |
| `soc_pct` | Battery state of charge in percent |
| `v_bus_v` | DC bus voltage |
| `v_batt_v` | Battery terminal voltage |
| `i_batt_a` | Battery current |
| `p_batt_w` | Measured battery power |
| `p_load_w` | Load power |
| `p_source_w` | Source power |
| `source_at_limit` | Flag indicating whether the source is power-limited |
| `source_available` | Flag indicating source availability |
| `fault_flags` | Dictionary of active model, communication, or plant faults |
| `extra` | Optional backend-specific metadata |

This observation is not intended to contain every simulator variable. Instead, it exposes the variables required for supervisory decision-making and safety monitoring. Additional internal variables remain inside the digital twin model.

### B. Command Contract

The command interface contains four fields:

**Table II. Digital twin command fields**

| Field | Description |
|---|---|
| `mode` | One of `CHARGE`, `HOLD`, `DISCHARGE`, or `SAFE` |
| `p_batt_cmd_w` | Battery power command in watts |
| `enable` | Boolean command-enable flag |
| `reason` | Human-readable command rationale |

The sign convention is:

```text
p_batt_cmd_w > 0: battery discharges into the bus
p_batt_cmd_w < 0: battery charges from the bus or source
p_batt_cmd_w = 0: hold
```

The `SAFE` mode disables command execution and sets the requested battery power to zero. In the Simulink implementation, the high-level command is converted to workspace variables or UDP message fields. The inner model maps the battery-power reference to converter-level control through the model's own controller.

### C. Goal Contract

The goal object defines both desired operating regions and hard safety limits. For the current case study, the goal includes:

```text
SOC target band: 40% to 80%
SOC hard limits: 10% to 95%
Bus nominal voltage: 400 V
Bus soft band: +/-5% of nominal
Bus hard band: +/-20% of nominal
Success hold time: configurable
Maximum mission time: configurable
Optional battery-current hard limit
```

The separation between soft and hard limits is central to the framework. Soft-limit violations are recorded and can guide policy action. Hard-limit violations cause deterministic safety termination.

### D. Guarded Runner Logic

The runner enforces several safety and validity checks:

1. Startup grace period: transient startup observations can be tolerated for a configurable period.
2. Hard-constraint checking: SOC, bus voltage, current limits, and active fault flags can trigger a safe stop.
3. Soft-constraint reporting: target-band violations are recorded in the mission log.
4. Command clipping: battery power commands are bounded by a configured maximum magnitude.
5. Command rate limiting: changes in commanded battery power are bounded per supervisor tick.
6. Disabled command behavior: disabled commands reset the held power command to zero.
7. Fallback behavior: AI policy failures can fall back to a deterministic policy.

These mechanisms are deliberately outside the policy. A policy may suggest an action, but the runner determines whether the action is executable.

### E. Algorithm

**Algorithm 1. Guarded autonomous digital twin supervisory loop**

```text
Input: backend B, policy pi, goal G, configuration C
Output: mission result R and event log E

1:  E <- empty list
2:  o <- B.reset()
3:  stable_time <- 0
4:  previous_command <- HOLD
5:  while o.sim_time_s < G.max_sim_time_s do
6:      hard <- hard_violations(o, G)
7:      soft <- soft_violations(o, G)
8:      if hard is not empty then
9:          u <- SAFE(reason=hard)
10:         B.apply_command(u)
11:         append event(o, u, safety_stopped, hard) to E
12:         return mission_result(safety_stopped, E)
13:     end if
14:     if goal_satisfied(o, G) and soft is empty then
15:         stable_time <- stable_time + elapsed_time
16:         if stable_time >= G.success_hold_s then
17:             u <- HOLD(reason=success)
18:             append event(o, u, succeeded, []) to E
19:             return mission_result(succeeded, E)
20:         end if
21:     else
22:         stable_time <- 0
23:     end if
24:     if o.sim_time_s < C.startup_grace_s then
25:         u_policy <- HOLD(reason=startup_grace)
26:     else
27:         u_policy <- pi.choose_action(o, G)
28:     end if
29:     u <- limit_command(u_policy, previous_command, C)
30:     B.apply_command(u)
31:     append event(o, u, running, soft) to E
32:     previous_command <- u
33:     o <- B.advance(C.supervisor_period_s)
34: end while
35: return mission_result(timed_out, E)
```

## VI. Policy Layer

### A. Deterministic Baseline Policy

The baseline policy is a deterministic state-of-charge and bus-voltage band policy. It first checks active fault flags. If faults are active, it requests a safe command. If bus voltage is below the soft lower limit and the battery is above the hard reserve, it requests battery discharge to support the bus. If bus voltage is above the soft upper limit and the battery is not near the upper target, it requests charging to absorb power. If SOC is below the target band and the source is available, it requests charging. If SOC is above the target band, it requests discharge. Otherwise, it holds.

This policy is intentionally simple. Its role is not to represent a final optimal controller. Its role is to provide a transparent baseline and fallback policy for framework development.

### B. AI and LLM-Based Policy Interface

The same policy interface can be implemented by an AI policy. In the current implementation, an OpenAI-compatible chat-completion client can be used as a high-level supervisory policy. The model receives a structured JSON payload containing the goal, observation, and required response schema. It must return one compact JSON object:

```json
{
  "mode": "CHARGE | HOLD | DISCHARGE | SAFE",
  "p_batt_cmd_w": 0.0,
  "reason": "short explanation"
}
```

The language model is not allowed to command duty ratio, switching states, or direct actuator values. It only proposes the high-level supervisory command. The runner then parses the JSON, converts it to the command object, clips the command, applies rate limits, and handles failures.

### C. Fallback and Strict Modes

If the AI policy fails to produce valid JSON or if the model call fails, the framework can fall back to the deterministic baseline policy. In strict experimental mode, the same failure can instead terminate the run and record the policy failure. This option is useful for separating control robustness experiments from AI-output-validity experiments.

### D. Trace Logging

For AI policies, the framework can log each model request, response, and fallback event as JSON lines. This enables post-run analysis of AI behavior, response validity, and policy rationale. Trace logging is separate from mission logging so that control events and model-interaction events can be analyzed independently.

## VII. Backend Layer

### A. Mock Backend

The mock backend is a deterministic battery/load-bus approximation. It is not intended to replace the Simulink model. Instead, it allows the runner, policy interface, guard layer, command limiting, mission status logic, and report generation to be tested before live model integration. This backend is useful for unit tests and early scenario design.

### B. MATLAB/Simulink Engine Backend

The MATLAB/Simulink backend uses MATLAB Engine to initialize the model, apply command variables, step the simulation, and extract observations. The backend expects command variables such as:

```text
P_batt_cmd
enable_cmd
mode_cmd
```

The bridge returns observations as JSON to avoid fragile MATLAB-to-Python struct conversion. This step-based backend is useful when the autonomous runner should directly control simulation advancement.

### C. Live UDP Backend

The live UDP backend supports a continuously running Simulink model. In this mode, Simulink sends observation packets to the Python runner and receives command packets from it. The runner does not call MATLAB Engine to advance the simulation. Instead, it waits for live observation packets and resends the latest command at a configurable interval.

The default communication pattern is:

```text
Simulink -> Python: observation packets
Python -> Simulink: command packets
Python -> monitor: optional telemetry republish
```

The UDP packet schema is compact JSON with a protocol name, version, packet kind, sequence number, timestamp, and command or observation payload. Commands include both string modes and numeric mode codes:

```text
CHARGE = -1
HOLD = 0
DISCHARGE = 1
SAFE = 99
```

The Simulink command receiver can include a stale-command timeout. If no fresh command arrives within the allowed time, the model can disable the command path and enter a safe mode. This creates a second safety layer inside the digital twin runtime.

## VIII. Case Study: Battery-Assisted DC Bus Digital Twin

### A. System Description

The framework is demonstrated using a battery-assisted DC load-bus digital twin. The digital twin includes a DC bus, source, load, battery, and converter-level control path. The autonomous supervisor is responsible for maintaining SOC within a target band while keeping bus voltage within a desired range. The supervisor does not directly control the converter duty ratio. Instead, it sends a battery-power command to the digital twin, and the model's internal controller maps that command to converter behavior.

This case study is representative of a broader class of power-system digital twin problems in which supervisory decisions must coordinate energy storage, load support, source limits, and safety constraints. The same framework can also be mapped to a laboratory DC microgrid with two parallel converter-interfaced sources, droop-based load sharing, a common DC bus, and a variable resistive load. In that setting, the observation and command contracts would be extended to include source currents, droop coefficients, load-sharing ratios, and bus-voltage regulation objectives.

### B. Supervisory Objective

The initial mission objective is:

```text
Maintain SOC inside the target band.
Maintain bus voltage inside the soft bus-voltage band.
Stop safely if SOC or bus voltage crosses hard limits.
Record each supervisory decision and constraint violation.
```

The target objective is intentionally modest. It is designed to validate the framework before introducing more complex optimization objectives such as energy management, adaptive droop coordination, or predictive scheduling.

### C. Implementation Summary

The implementation includes:

1. `AutonomousRunner`, which implements the guarded supervisory loop.
2. `DTObservation`, `DTCommand`, and `DTGoal`, which define the state-action-goal contract.
3. `SocBandPolicy`, which provides a deterministic baseline policy.
4. `LLMControlPolicy`, which provides an OpenAI-compatible AI policy.
5. `MockBatteryBusBackend`, which supports deterministic local testing.
6. `SimulinkBackend`, which supports MATLAB/Simulink engine execution.
7. `UdpLiveSimulinkBackend`, which supports live model communication.
8. Mission reporting utilities, which generate CSV and Markdown audit logs.

### D. Example Mission Evidence

The current prototype produces mission reports containing:

```text
mission status
mission reason
number of supervisor decisions
simulation time range
SOC start and end values
bus-voltage start and end values
telemetry min and max values
commanded power min and max values
mode counts
constraint violations
decision timeline
```

This format provides a direct audit trail for each run. For example, nominal mock-backend runs can show repeated `HOLD` decisions when SOC and bus voltage are inside the target band. Low-SOC or bus-support scenarios can show `CHARGE` or `DISCHARGE` decisions depending on source availability and bus voltage. Hard-limit scenarios can show deterministic transition to `SAFE` mode.

Because this is a framework paper, the final experimental section should emphasize scenario coverage and architectural behavior rather than claim controller optimality.

## IX. Evaluation Protocol

The proposed evaluation should answer four framework-level questions:

1. Does the framework preserve safety constraints independently of the active policy?
2. Can different policies be substituted through the same interface?
3. Can the same runner operate over mock, step-based Simulink, and live UDP backends?
4. Does the reporting layer produce enough evidence to audit each decision?

### A. Demonstration Scenarios

The final manuscript should include the scenario matrix shown in Table III after final experiments are run.

**Table III. Planned demonstration scenario matrix**

| Scenario | Initial condition or disturbance | Expected framework behavior | Primary metric |
|---|---|---|---|
| Nominal in-band operation | SOC and bus voltage inside target bands | Hold command, no violations | Correct hold behavior |
| Low SOC with available source | SOC below target, source available | Charge command subject to limits | Correct mode and bounded power |
| Low bus voltage | Bus voltage below soft band, SOC above reserve | Discharge for bus support | Voltage-support response |
| High SOC | SOC above target band | Discharge or hold depending on bus state | SOC-band response |
| Hard SOC violation | SOC at or below hard reserve, or at or above hard maximum | Immediate safe stop | Safety-stop correctness |
| Communication interruption | Missing or stale UDP commands or observations | Timeout, fallback, or safe behavior | Communication robustness |
| AI malformed output | Invalid JSON or invalid mode | Fallback or strict failure | Policy-failure handling |
| Backend substitution | Same scenario across mock and Simulink backends | Same runner and policy interface | Backend portability |

### B. Metrics

The framework should be evaluated using metrics aligned with guarded supervisory control:

```text
task success rate
hard-constraint violation count
soft-constraint violation count and duration
safe-stop correctness
command validity rate
command clipping frequency
command rate-limit activation frequency
AI fallback rate
communication timeout count
decision latency
audit-log completeness
backend portability across scenarios
```

For a framework paper, these metrics are more appropriate than a single control-performance number. They evaluate whether the architecture creates a reliable experimental platform for autonomous digital twin control.

### C. Baselines and Ablations

The following comparisons are recommended:

1. Deterministic baseline policy with guard layer.
2. AI policy with guard layer.
3. AI policy in strict mode to measure raw AI-output validity.
4. Guarded policy with command rate limiting disabled in simulation-only testing.
5. Mock backend versus Simulink backend for equivalent scenario definitions.
6. Step-based Simulink bridge versus live UDP communication.

An unguarded AI policy should not be run against a live or physical system. If included, it should be restricted to offline simulation to illustrate the value of guard enforcement.

### D. Results Table Template

The final paper should include a compact table such as Table IV.

**Table IV. Results template for final experiments**

| Scenario | Backend | Policy | Status | Hard violations | Soft violations | Final SOC (%) | Final Vbus (V) | Fallbacks | Notes |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| Nominal | Mock | Deterministic | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| Nominal | Simulink | Deterministic | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| Low SOC | Mock | Deterministic | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| Low SOC | Simulink | AI | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| UDP live | Simulink UDP | AI | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

The key claim should be that the framework captures, bounds, and reports each run consistently across policies and backends.

## X. Discussion

The proposed framework addresses a practical gap between digital twin modeling and autonomous control. Many digital twin architectures emphasize representation, synchronization, and visualization. Many control architectures emphasize plant-level control design. The proposed framework focuses on the layer between them: the guarded autonomous supervisor that treats the digital twin as an executable runtime while preserving explicit safety and audit contracts.

The framework is especially useful when experimenting with AI-based policies. Language models and other learned policies may offer flexible reasoning, natural-language rationales, or adaptation to structured context. However, they should not be treated as safety-critical controllers. In this framework, the AI policy is an interchangeable proposal generator. It can suggest a high-level command, but the runner checks constraints, clips commands, rate-limits power, and decides whether to continue or stop.

The backend abstraction also improves development workflow. Researchers can begin with a deterministic mock backend to validate runner logic and scenario definitions. They can then use MATLAB/Simulink engine integration for controlled step-based simulation. Finally, they can move to live UDP communication when the digital twin is running continuously. This progression reduces the risk of debugging AI behavior, communication behavior, and plant-model behavior simultaneously.

The case study also highlights the importance of separating supervisory objectives from inner-loop control. For a converter-interfaced power system, directly commanding duty ratio from an AI policy would be inappropriate. A power reference, mode command, or droop-adjustment command is more suitable for the autonomous supervisory layer. This design choice makes the framework more transferable to other cyber-physical systems where low-level control must remain deterministic and fast.

## XI. Limitations and Future Work

The present framework has several limitations. First, the current case-study objective is intentionally simple. Maintaining SOC and bus voltage bands demonstrates the framework but does not fully exploit predictive digital twin capabilities. Future work should include forecast-aware energy management, adaptive load-sharing, and multi-objective optimization.

Second, the current command space is compact. More complex microgrid scenarios may require commands for droop coefficients, source dispatch, load shedding, operating-mode transitions, or fault-isolation decisions. The framework supports this extension, but the state-action contract must be expanded carefully.

Third, the current implementation focuses on supervisory control in simulation and live digital twin environments. Physical hardware integration would require additional safety certification, real-time guarantees, hardware interlocks, and operator approval pathways.

Fourth, AI-policy evaluation remains preliminary. The framework can host a language-model policy, but final claims about AI control quality require a larger scenario set, controlled baselines, repeated trials, and careful analysis of malformed outputs, latency, and fallback frequency.

Fifth, UDP communication is useful for live desktop simulation, but production or real-time deployments may require more robust middleware, deterministic networking, authentication, and time synchronization.

Future work will extend the framework in four directions:

1. A richer microgrid case study with adaptive droop and load-sharing control.
2. Scenario libraries for repeatable autonomous digital twin benchmarking.
3. Formal policy-safety contracts for learned and language-model-based supervisors.
4. Integration with operator-in-the-loop approval and explanation workflows.

## XII. Conclusion

This paper proposed a modular framework for guarded autonomous digital twin supervisory control. The framework defines a structured observation, goal, command, policy, backend, guard, and reporting architecture. It separates high-level policy proposals from deterministic safety enforcement and backend execution. It supports deterministic and AI-based policies through a common interface, and it can operate over mock simulation, MATLAB/Simulink engine control, and live UDP communication. A battery-assisted DC bus digital twin case study demonstrates how the framework can be instantiated for power-system supervisory control while preserving auditability and safety constraints.

The main contribution is not a single controller tuned for one scenario. Rather, the contribution is a reusable architecture for developing, testing, and evaluating autonomous digital twin controllers. By making the state-action contract explicit, keeping safety outside the policy, and recording each decision, the framework provides a practical path from passive digital twins toward guarded autonomous digital twin operation.

## References

TODO: Replace these placeholders with IEEE-formatted references after the target special call and final literature set are confirmed.

[1] Digital twin survey or foundational definition reference.

[2] Digital twin reference for cyber-physical systems or power systems.

[3] Digital twin control or autonomous digital twin framework reference.

[4] Microgrid or DC bus supervisory control reference.

[5] Battery energy storage control reference.

[6] Simulink or model-based design reference if permitted by venue style.

[7] Guarded autonomy or safe reinforcement learning reference.

[8] LLM agents or tool-use policy reference, if the AI-policy portion remains in the submitted version.

[9] Prior hierarchical or image-based digital twin work from the local project literature set.

[10] Prior DC microgrid digital twin forecasting or control work from the local project literature set.

## Author Revision Checklist

Before submission:

1. Recover the exact IEEE special-call title, scope, page limit, and template requirements.
2. Replace the title if the call uses specific keywords such as "autonomous digital twins", "AI-enabled digital twins", "industrial informatics", or "power systems".
3. Add author names, affiliations, acknowledgments, and funding information.
4. Convert this Markdown draft into the correct IEEE Word or LaTeX template.
5. Insert final figures:
   - framework block diagram;
   - guarded control-loop diagram;
   - backend architecture diagram;
   - case-study digital twin diagram.
6. Run final demonstration scenarios and fill Tables III and IV.
7. Replace all reference placeholders with verified IEEE-formatted citations.
8. Tighten the claims so that every experimental statement is supported by a log, figure, table, or code artifact.
