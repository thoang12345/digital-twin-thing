from typing import Any, Callable, Dict, List, Tuple

from Modules.Digital_Twins.tool_runner import run_autonomous_DT
from Modules.Tools.finish import finish


def _function_tool(
    name: str,
    description: str,
    properties: Dict[str, Any],
    required: List[str],
) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def build_default_toolset(
    dt_state_manager,
    chroma_tools,
) -> Tuple[List[Dict[str, Any]], Dict[str, Callable[..., Dict[str, Any]]]]:
    tool_registry = {
        "get_DT_state": dt_state_manager.get_DT_state,
        "set_DT_state": dt_state_manager.set_DT_state,
        "search_DT_info": chroma_tools.search_DT_info,
        "find_DT_by_output": chroma_tools.find_DT_by_output,
        "find_DT_by_input": chroma_tools.find_DT_by_input,
        "search_long_term_memory": chroma_tools.search_long_term_memory,
        "run_autonomous_DT": run_autonomous_DT,
        "finish": finish,
    }

    tools = [
        _function_tool(
            name="get_DT_state",
            description="Get the current status of a digital twin model.",
            properties={
                "dt_name": {
                    "type": "string",
                    "description": "The digital twin model name.",
                }
            },
            required=["dt_name"],
        ),
        _function_tool(
            name="set_DT_state",
            description="Set a digital twin model state to activate or deactivate.",
            properties={
                "dt_name": {
                    "type": "string",
                    "description": "The digital twin model name.",
                },
                "state": {
                    "type": "string",
                    "description": "The desired state: activate or deactivate.",
                    "enum": ["activate", "deactivate"],
                },
            },
            required=["dt_name", "state"],
        ),
        _function_tool(
            name="search_DT_info",
            description="Search the digital twin knowledge base for descriptions, inputs, outputs, and other metadata.",
            properties={
                "query": {
                    "type": "string",
                    "description": "The search query.",
                }
            },
            required=["query"],
        ),
        _function_tool(
            name="find_DT_by_output",
            description="Find which digital twin models produce a given output signal.",
            properties={
                "output_name": {
                    "type": "string",
                    "description": "The output signal to look up.",
                }
            },
            required=["output_name"],
        ),
        _function_tool(
            name="find_DT_by_input",
            description="Find which digital twin models require a given input signal.",
            properties={
                "input_name": {
                    "type": "string",
                    "description": "The input signal to look up.",
                }
            },
            required=["input_name"],
        ),
        _function_tool(
            name="search_long_term_memory",
            description="Search the long-term memory store for previous technical context.",
            properties={
                "query": {
                    "type": "string",
                    "description": "The memory search query.",
                }
            },
            required=["query"],
        ),
        _function_tool(
            name="run_autonomous_DT",
            description=(
                "Run an autonomous battery/load-bus digital twin mission and "
                "return the mission status, final observation, recent decisions, "
                "and report/CSV artifact paths. Use backend='mock' for safe "
                "offline checks, backend='simulink' for MATLAB Engine chunked "
                "simulation, or backend='udp' for a live Simulink model that is "
                "already running and exchanging UDP packets."
            ),
            properties={
                "backend": {
                    "type": "string",
                    "enum": ["mock", "simulink", "udp"],
                    "description": "Runtime backend. Use udp only when the Simulink model is already running live.",
                },
                "policy": {
                    "type": "string",
                    "enum": ["heuristic", "llm"],
                    "description": "Decision policy. heuristic is deterministic; llm calls an OpenAI-compatible policy model.",
                },
                "max_sim_seconds": {
                    "type": "number",
                    "description": "Maximum simulated mission duration in seconds.",
                },
                "tick_seconds": {
                    "type": "number",
                    "description": "Supervisor decision interval in seconds.",
                },
                "startup_grace_seconds": {
                    "type": "number",
                    "description": "Initial seconds where startup transients are tolerated and battery command is held.",
                },
                "success_hold_seconds": {
                    "type": "number",
                    "description": "How long the goal must remain satisfied before success.",
                },
                "soc_min": {
                    "type": "number",
                    "description": "Target SOC lower bound in percent.",
                },
                "soc_max": {
                    "type": "number",
                    "description": "Target SOC upper bound in percent.",
                },
                "bus_nominal": {
                    "type": "number",
                    "description": "Nominal DC bus voltage.",
                },
                "max_p_batt": {
                    "type": "number",
                    "description": "Absolute battery command power limit in watts.",
                },
                "max_p_batt_step": {
                    "type": "number",
                    "description": "Maximum command power change per supervisor tick in watts.",
                },
                "prevent_source_backfeed": {
                    "type": "boolean",
                    "description": "When true, cap battery discharge so a one-quadrant source is not driven into reverse power.",
                },
                "source_min_power": {
                    "type": "number",
                    "description": "Minimum source power in watts to preserve when preventing source backfeed.",
                },
                "source_power_margin": {
                    "type": "number",
                    "description": "Conservative source power margin in watts used by the no-backfeed discharge cap.",
                },
                "source_power_limit": {
                    "type": "number",
                    "description": "Optional source power capacity in watts used for charge-headroom limiting.",
                },
                "prevent_charge_without_source_headroom": {
                    "type": "boolean",
                    "description": "When true, block or cap charging when source headroom is unavailable.",
                },
                "charge_power_margin": {
                    "type": "number",
                    "description": "Conservative source power margin in watts preserved before charging.",
                },
                "charge_bus_hysteresis_volts": {
                    "type": "number",
                    "description": "Bus-voltage recovery margin above the soft minimum before charging can resume.",
                },
                "charge_recovery_hold_seconds": {
                    "type": "number",
                    "description": "Cooldown after a charge block before charging can be retried.",
                },
                "post_discharge_charge_hold_seconds": {
                    "type": "number",
                    "description": "Cooldown before charging can resume after battery discharge was used for bus/source support.",
                },
                "block_discharge_below_soc_min": {
                    "type": "boolean",
                    "description": "When true, block discretionary battery discharge below the target SOC minimum unless the bus is low or source support is needed.",
                },
                "allow_source_support_below_soc_min": {
                    "type": "boolean",
                    "description": "When true, allow low-SOC discharge only to cover a real load-over-source deficit.",
                },
                "source_support_entry_margin": {
                    "type": "number",
                    "description": "Minimum load-over-source deficit in watts before low-SOC source support becomes active.",
                },
                "source_support_clear_margin": {
                    "type": "number",
                    "description": "Source deficit in watts below which the source-support latch can clear.",
                },
                "source_support_bus_hysteresis_volts": {
                    "type": "number",
                    "description": "Bus-voltage margin above the soft minimum required before the source-support latch can clear.",
                },
                "source_support_hold_seconds": {
                    "type": "number",
                    "description": "Seconds the source-support latch must see a clear condition before resetting.",
                },
                "bus_support_min": {
                    "type": "number",
                    "description": "Minimum battery discharge target in watts when bus voltage is below the soft minimum.",
                },
                "bus_support_gain": {
                    "type": "number",
                    "description": "Battery discharge target gain in watts per volt of bus voltage error below nominal.",
                },
                "safety_recovery": {
                    "type": "boolean",
                    "description": "When true and policy='llm', recoverable hard voltage/SOC violations trigger an LLM safety-recovery pass before full safe stop.",
                },
                "safety_recovery_attempts": {
                    "type": "integer",
                    "description": "Maximum consecutive LLM safety-recovery attempts before declaring full safe stop.",
                },
                "initial_soc": {
                    "type": "number",
                    "description": "Initial SOC used only by the mock backend.",
                },
                "real_time": {
                    "type": "boolean",
                    "description": "Sleep between supervisor ticks. Usually false except for live demos.",
                },
                "model_path": {
                    "type": "string",
                    "description": "Optional .slx path for backend='simulink'.",
                },
                "model_name": {
                    "type": "string",
                    "description": "Simulink model name for backend='simulink'.",
                },
                "udp_command_host": {
                    "type": "string",
                    "description": "Host where live Simulink receives UDP commands.",
                },
                "udp_command_port": {
                    "type": "integer",
                    "description": "UDP command port used by the Simulink receiver.",
                },
                "udp_observation_port": {
                    "type": "integer",
                    "description": "Local UDP port where the agent listens for Simulink observations.",
                },
                "udp_reset_timeout": {
                    "type": "number",
                    "description": "Seconds to wait for the first UDP observation.",
                },
                "udp_timeout": {
                    "type": "number",
                    "description": "Seconds to wait for each UDP observation after reset.",
                },
                "llm_model": {
                    "type": "string",
                    "description": "OpenAI-compatible policy model name when policy='llm'.",
                },
                "llm_base_url": {
                    "type": "string",
                    "description": "OpenAI-compatible base URL when policy='llm'.",
                },
                "llm_api_key": {
                    "type": "string",
                    "description": "API key for the policy LLM when policy='llm'.",
                },
                "llm_max_tokens": {
                    "type": "integer",
                    "description": "Maximum tokens for each compact LLM decision response.",
                },
                "llm_command_limit": {
                    "type": "number",
                    "description": "Maximum absolute wattage the LLM is asked to use in its decision JSON.",
                },
                "llm_mode_gate": {
                    "type": "boolean",
                    "description": "If true, reject LLM modes that disagree with the deterministic SOC/bus policy. Leave false when studying LLM control behavior.",
                },
                "llm_strict": {
                    "type": "boolean",
                    "description": "If true, LLM policy errors fail the mission instead of falling back.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory where CSV/report/LLM trace artifacts are written.",
                },
                "run_label": {
                    "type": "string",
                    "description": "Short label included in artifact filenames.",
                },
            },
            required=[],
        ),
        _function_tool(
            name="finish",
            description="Return the final response to the user once enough information has been gathered.",
            properties={
                "final_response": {
                    "type": "string",
                    "description": "The final response to send back to the user.",
                }
            },
            required=["final_response"],
        ),
    ]

    return tools, tool_registry
