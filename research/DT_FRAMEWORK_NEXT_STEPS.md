# DT Framework Next Steps

This branch shifts the project from a retrieval-heavy prototype toward a framework paper on end-to-end digital twin assistants.

## Target framing for the paper

The paper should not read as:

- "here is my app"

It should read as:

- "here is a modular framework for LLM-driven digital twin assistants that combines structured twin representations, retrieval, orchestration, runtime adapters, and guarded action reasoning"

That means the main artifact is the framework architecture and its evaluation, not the current GUI or product wrapper.

## The gap from the V2 baseline

The baseline already has:

- modular orchestration
- retrieval
- smart ingestion
- benchmark scaffolding
- a thin DT metadata/state layer

The baseline does not yet have:

- a formal digital twin schema
- a twin registry
- runtime adapters for live or replayed twin data
- cross-twin dependency reasoning
- simulation / what-if execution
- guarded action planning
- end-to-end DT task benchmarks

## The recommended implementation order

The order matters.
If we build orchestration before we formalize what a twin is, the framework will stay fuzzy.

### Step 1. Formalize the digital twin abstraction layer

Goal:
define the canonical representation of a twin in this framework.

What to add:

- twin identity
- domain / asset / subsystem
- inputs
- outputs
- state variables
- controllable parameters
- update cadence
- dependency links
- uncertainty or confidence metadata
- allowed actions
- safety constraints

Suggested new module area:

- `Modules/DigitalTwin/`

Suggested first files:

- `Modules/DigitalTwin/types.py`
- `Modules/DigitalTwin/registry.py`
- `Modules/DigitalTwin/constraints.py`

Expected outcome:

- the system can reason over twins as structured objects, not only as Chroma text matches

### Step 2. Add a twin registry

Goal:
store and query the available twins in a structured, framework-level registry.

The registry should answer questions like:

- what twins exist?
- what outputs does each twin produce?
- what inputs does each twin require?
- which signals are shared across twins?
- which twin can answer this question or support this task?

This should replace the current hardcoded feel of the DT layer with something explicit and inspectable.

### Step 3. Define adapter interfaces for runtime access

Goal:
let the assistant interact with actual twin backends or controlled simulations.

Suggested interface shape:

- `get_state(twin_id)`
- `get_history(twin_id, signal, window)`
- `run_simulation(twin_id, scenario)`
- `set_parameter(twin_id, parameter, value)`
- `compare_predicted_vs_observed(twin_id)`

Suggested files:

- `Modules/DigitalTwin/adapters/base.py`
- `Modules/DigitalTwin/adapters/mock.py`
- later, domain-specific adapters as needed

Important note:

for the paper, replay-based or mock adapters are completely acceptable if the interface is clear and the scenarios are meaningful.

### Step 4. Build dependency-aware reasoning

Goal:
move from single-twin lookup to cross-twin orchestration.

Examples:

- sensor stream -> fusion twin -> state estimation twin -> degradation twin
- fault in one upstream signal -> downstream confidence drop
- missing input in one twin -> alternate route or fallback recommendation

Suggested files:

- `Modules/DigitalTwin/dependency_graph.py`
- `Modules/DigitalTwin/resolution.py`

Expected outcome:

- the assistant can trace impact, not just retrieve definitions

### Step 5. Add guarded action planning

Goal:
support end-to-end operational reasoning without jumping straight to unsafe autonomy.

Recommended progression:

1. inspect
2. retrieve evidence
3. infer candidate action
4. simulate or validate
5. recommend
6. optionally execute under explicit guardrails

This is the point where the assistant becomes more than RAG plus tools.

Suggested files:

- `Modules/DigitalTwin/planner.py`
- `Modules/DigitalTwin/policies.py`
- `Modules/DigitalTwin/execution.py`

### Step 6. Add operational memory

Goal:
store more than chat history.

Needed memory types:

- previous twin states
- past operator actions
- previous diagnoses
- previous recommendations
- previous simulation outcomes

This can later support:

- better explanations
- repeated-task improvement
- auditability

### Step 7. Build end-to-end benchmarks

Goal:
prove the framework works as a DT assistant, not just as a retrieval system.

Suggested benchmark task categories:

- twin selection
- input/output tracing
- fault localization
- dependency impact analysis
- missing-signal diagnosis
- what-if scenario evaluation
- safe activation/deactivation sequencing
- recommendation generation with evidence

Suggested metrics:

- task success rate
- correct twin selection
- correct dependency trace
- correct action recommendation
- retrieval support quality
- latency
- explanation completeness / provenance

## What we should treat as the first real coding milestone

The first implementation step on this branch should be:

- formal twin schema
- registry
- registry-backed lookup tools

That step is small enough to understand clearly and big enough to change the architecture in the right direction.

## What should stay from the baseline

We should keep and reuse:

- the tool loop
- the modular project layout
- the retrieval pipeline
- the ingestion pipeline
- the benchmarking style
- the GUI only as a development aid, not as the paper centerpiece

## What will likely be rewritten or expanded

- DT tool catalog
- DT state manager
- DT collections and structured metadata conventions
- runtime settings around which collection is the canonical twin registry
- evaluation layer to include task benchmarks, not only retrieval benchmarks

## A good immediate reading / design sequence for this branch

1. re-read `docs/BASELINE_V2_WALKTHROUGH.md`
2. inspect `Modules/Tools/dt_state.py`
3. inspect `Modules/Tools/tool_catalog.py`
4. inspect `Modules/Tools/search_tools.py`
5. write down the twin schema we actually want
6. then build the registry around that schema

That sequence keeps us grounded in what exists before we replace it.
