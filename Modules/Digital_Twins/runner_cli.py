from __future__ import annotations

import argparse
from pathlib import Path

from openai import OpenAI

from Modules.Digital_Twins.backends import MockBatteryBusBackend, SimulinkBackend
from Modules.Digital_Twins.gui_events import format_dt_gui_event
from Modules.Digital_Twins.policy import LLMControlPolicy, SocBandPolicy
from Modules.Digital_Twins.reporting import write_mission_report
from Modules.Digital_Twins.runner import AutonomousRunner, write_runner_events_csv
from Modules.Digital_Twins.types import DTGoal, RunnerConfig, RunnerResult
from Modules.Digital_Twins.udp_backend import UdpLiveSimulinkBackend


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the autonomous battery/load-bus DT supervisor."
    )
    parser.add_argument(
        "--backend",
        choices=["mock", "simulink", "udp"],
        default="mock",
        help="Simulation backend to control.",
    )
    parser.add_argument(
        "--policy",
        choices=["heuristic", "llm"],
        default="heuristic",
        help="Decision policy. Use llm to let the AI propose bounded commands.",
    )
    parser.add_argument("--soc-min", type=float, default=40.0)
    parser.add_argument("--soc-max", type=float, default=80.0)
    parser.add_argument("--initial-soc", type=float, default=55.0)
    parser.add_argument("--bus-nominal", type=float, default=400.0)
    parser.add_argument("--tick-seconds", type=float, default=5.0)
    parser.add_argument("--startup-grace-seconds", type=float, default=1.0)
    parser.add_argument("--max-sim-seconds", type=float, default=600.0)
    parser.add_argument("--success-hold-seconds", type=float, default=60.0)
    parser.add_argument("--max-p-batt", type=float, default=500.0)
    parser.add_argument("--max-p-batt-step", type=float, default=100.0)
    parser.add_argument(
        "--source-min-power",
        type=float,
        default=0.0,
        help=(
            "Minimum source power to preserve when preventing source backfeed. "
            "Use 0 for a source that can reduce to zero but cannot sink power."
        ),
    )
    parser.add_argument(
        "--source-power-margin",
        type=float,
        default=25.0,
        help=(
            "Conservative source power margin in watts used by the no-backfeed "
            "guard. Battery discharge is capped below load demand by this margin."
        ),
    )
    parser.add_argument(
        "--source-power-limit",
        type=float,
        default=None,
        help=(
            "Optional source power capacity in watts. Used as a fallback for "
            "charge-headroom limiting when telemetry does not provide "
            "source_power_limit_w."
        ),
    )
    parser.add_argument(
        "--allow-charge-without-source-headroom",
        action="store_true",
        help="Disable the default guard that blocks charging when source headroom is unavailable.",
    )
    parser.add_argument(
        "--charge-power-margin",
        type=float,
        default=25.0,
        help="Conservative source power margin in watts preserved before charging.",
    )
    parser.add_argument(
        "--charge-bus-hysteresis-volts",
        type=float,
        default=5.0,
        help="Bus-voltage recovery margin above the soft minimum before charging can resume.",
    )
    parser.add_argument(
        "--charge-recovery-hold-seconds",
        type=float,
        default=10.0,
        help="Cooldown after a charge block before charging can be retried.",
    )
    parser.add_argument(
        "--post-discharge-charge-hold-seconds",
        type=float,
        default=10.0,
        help=(
            "Cooldown before charging can resume after battery discharge was "
            "used for bus/source support."
        ),
    )
    parser.add_argument(
        "--allow-source-backfeed",
        action="store_true",
        help="Disable the default guard that prevents battery discharge from pushing reverse power into the source.",
    )
    parser.add_argument(
        "--allow-discharge-below-soc-min",
        action="store_true",
        help="Disable the default guard that blocks discretionary discharge below the target SOC minimum.",
    )
    parser.add_argument(
        "--disable-source-support-below-soc-min",
        action="store_true",
        help=(
            "Disable the default exception that allows low-SOC battery "
            "discharge only when load demand exceeds source capacity."
        ),
    )
    parser.add_argument(
        "--source-support-entry-margin",
        type=float,
        default=5.0,
        help=(
            "Minimum load-over-source deficit in watts before low-SOC source "
            "support is considered active."
        ),
    )
    parser.add_argument(
        "--source-support-clear-margin",
        type=float,
        default=1.0,
        help="Source deficit in watts below which the source-support latch can clear.",
    )
    parser.add_argument(
        "--source-support-bus-hysteresis-volts",
        type=float,
        default=5.0,
        help=(
            "Bus-voltage margin above the soft minimum required before the "
            "source-support latch can clear."
        ),
    )
    parser.add_argument(
        "--source-support-hold-seconds",
        type=float,
        default=3.0,
        help="Seconds the source-support latch must see a clear condition before resetting.",
    )
    parser.add_argument(
        "--bus-support-min",
        type=float,
        default=150.0,
        help=(
            "Minimum battery discharge target in watts when bus voltage is "
            "below the soft minimum."
        ),
    )
    parser.add_argument(
        "--bus-support-gain",
        type=float,
        default=5.0,
        help=(
            "Battery discharge target gain in watts per volt of bus voltage "
            "error below nominal."
        ),
    )
    parser.add_argument(
        "--bus-support-integral-gain",
        type=float,
        default=0.0,
        help=(
            "Leaky integral gain in watts per volt-second for bus support. "
            "Default 0 disables integral action."
        ),
    )
    parser.add_argument(
        "--bus-support-integral-max",
        type=float,
        default=20.0,
        help="Maximum bus-support integral contribution in watts.",
    )
    parser.add_argument(
        "--bus-support-integral-leak",
        type=float,
        default=0.25,
        help=(
            "Fraction of bus-support integral state leaked per second after "
            "the bus-support voltage error clears. Use 0 to disable leakage."
        ),
    )
    parser.add_argument(
        "--bus-support-integral-deadband-volts",
        type=float,
        default=0.25,
        help=(
            "Deadband below nominal bus voltage before bus-support integral "
            "error accumulates."
        ),
    )
    parser.add_argument(
        "--bus-support-trim-gain",
        type=float,
        default=0.0,
        help=(
            "Slow learned bus-support trim gain in watts per volt-second. "
            "Default 0 disables learned trim."
        ),
    )
    parser.add_argument(
        "--bus-support-trim-max",
        type=float,
        default=12.0,
        help="Maximum learned bus-support trim contribution in watts.",
    )
    parser.add_argument(
        "--bus-support-trim-decay",
        type=float,
        default=0.25,
        help=(
            "Watts per second removed from learned bus-support trim when "
            "the bus is recovered and the source is visibly below its limit."
        ),
    )
    parser.add_argument(
        "--bus-support-trim-deadband-volts",
        type=float,
        default=0.25,
        help=(
            "Deadband below nominal bus voltage before learned bus-support "
            "trim accumulates."
        ),
    )
    parser.add_argument(
        "--bus-support-trim-source-slack-deadband",
        type=float,
        default=2.0,
        help=(
            "Source slack in watts ignored before learned bus-support trim "
            "decays."
        ),
    )
    parser.add_argument(
        "--bus-support-target-slew-down",
        type=float,
        default=0.0,
        help=(
            "Maximum watts per second that bus_support_target_w may decrease. "
            "Default 0 disables target down-slew."
        ),
    )
    parser.add_argument(
        "--safety-recovery",
        action="store_true",
        help=(
            "On recoverable hard violations, apply a neutral safe command, ask "
            "the LLM policy for a bounded recovery command, and only fully "
            "safe-stop if recovery fails or attempts are exhausted."
        ),
    )
    parser.add_argument(
        "--safety-recovery-attempts",
        type=int,
        default=2,
        help="Maximum consecutive LLM safety-recovery attempts before full safe stop.",
    )
    parser.add_argument(
        "--real-time",
        action="store_true",
        help="Sleep wall-clock time between supervisor ticks.",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Optional path for runner audit CSV output.",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional path for Markdown mission report output.",
    )
    parser.add_argument(
        "--emit-gui-events",
        action="store_true",
        help=(
            "Print one compact DT_GUI_EVENT JSON line per supervisory decision. "
            "Used by the Tkinter authority-chain display."
        ),
    )
    parser.add_argument(
        "--model-name",
        default="DT_enviroment",
        help="Simulink model name used by --backend simulink.",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Optional .slx path used by --backend simulink.",
    )
    parser.add_argument(
        "--udp-command-host",
        default="127.0.0.1",
        help="Host/IP where live Simulink receives UDP command packets.",
    )
    parser.add_argument(
        "--udp-command-port",
        type=int,
        default=55000,
        help="UDP port where live Simulink receives command packets.",
    )
    parser.add_argument(
        "--udp-observation-host",
        default="0.0.0.0",
        help="Local interface used to listen for Simulink observation packets.",
    )
    parser.add_argument(
        "--udp-observation-port",
        type=int,
        default=55001,
        help="Local UDP port used to receive Simulink observation packets.",
    )
    parser.add_argument(
        "--udp-timeout",
        type=float,
        default=2.0,
        help="Seconds to wait for each live Simulink observation packet.",
    )
    parser.add_argument(
        "--udp-reset-timeout",
        type=float,
        default=5.0,
        help="Seconds to wait for the first live Simulink observation packet.",
    )
    parser.add_argument(
        "--udp-command-resend-period",
        type=float,
        default=0.25,
        help="Seconds between best-effort repeats of the latest UDP command.",
    )
    parser.add_argument(
        "--udp-send-reset",
        action="store_true",
        help="Send a best-effort reset control packet before waiting for telemetry.",
    )
    parser.add_argument(
        "--udp-republish-host",
        default=None,
        help="Optional host/IP where received observations should be republished.",
    )
    parser.add_argument(
        "--udp-republish-port",
        type=int,
        default=None,
        help="Optional UDP port where received observations should be republished.",
    )
    parser.add_argument(
        "--llm-model",
        default="llama-3-groq-8b-tool-use",
        help="OpenAI-compatible model name used by --policy llm.",
    )
    parser.add_argument(
        "--llm-base-url",
        default="http://localhost:1234/v1",
        help="OpenAI-compatible API base URL used by --policy llm.",
    )
    parser.add_argument(
        "--llm-api-key",
        default="lm-studio",
        help="API key used by --policy llm.",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=0.0,
        help="Sampling temperature used by --policy llm.",
    )
    parser.add_argument(
        "--llm-max-tokens",
        type=int,
        default=120,
        help="Maximum tokens allowed for each compact LLM decision response.",
    )
    parser.add_argument(
        "--llm-command-limit",
        type=float,
        default=500.0,
        help="Maximum absolute wattage the LLM is asked to use in its decision JSON.",
    )
    parser.add_argument(
        "--llm-mode-gate",
        action="store_true",
        help=(
            "Reject LLM modes that disagree with the deterministic SOC/bus policy. "
            "Leave off when studying LLM control behavior."
        ),
    )
    parser.add_argument(
        "--llm-log",
        default=None,
        help="Optional JSONL trace path for LLM requests, responses, and fallbacks.",
    )
    parser.add_argument(
        "--append-llm-log",
        action="store_true",
        help=(
            "Append to an existing --llm-log file instead of starting a fresh "
            "trace for this run."
        ),
    )
    parser.add_argument(
        "--llm-verbose",
        action="store_true",
        help="Print each LLM policy request/response/fallback to the console.",
    )
    parser.add_argument(
        "--llm-strict",
        action="store_true",
        help="Fail the mission instead of silently falling back if the LLM call fails.",
    )
    return parser.parse_args()


def build_backend(args: argparse.Namespace):
    if args.backend == "mock":
        return MockBatteryBusBackend(
            initial_soc_pct=args.initial_soc,
            bus_nominal_v=args.bus_nominal,
        )
    if args.backend == "simulink":
        return SimulinkBackend(
            model_name=args.model_name,
            model_path=args.model_path,
        )
    return UdpLiveSimulinkBackend(
        command_host=args.udp_command_host,
        command_port=args.udp_command_port,
        observation_host=args.udp_observation_host,
        observation_port=args.udp_observation_port,
        receive_timeout_s=args.udp_timeout,
        reset_timeout_s=args.udp_reset_timeout,
        command_resend_period_s=args.udp_command_resend_period,
        send_reset_on_reset=args.udp_send_reset,
        telemetry_host=args.udp_republish_host,
        telemetry_port=args.udp_republish_port,
    )


def build_policy(args: argparse.Namespace):
    if args.policy == "heuristic":
        return SocBandPolicy()

    client = OpenAI(
        base_url=args.llm_base_url,
        api_key=args.llm_api_key,
    )
    return LLMControlPolicy(
        client=client,
        model=args.llm_model,
        temperature=args.llm_temperature,
        max_tokens=args.llm_max_tokens,
        max_command_abs_w=args.llm_command_limit,
        mode_gate=args.llm_mode_gate,
        trace_path=args.llm_log,
        verbose=args.llm_verbose,
        strict=args.llm_strict,
    )


class MissionArtifactCheckpointer:
    """Best-effort writer that keeps report artifacts current during a run."""

    def __init__(
        self,
        *,
        goal: DTGoal,
        csv_path: str | None,
        report_path: str | None,
    ) -> None:
        self.goal = goal
        self.csv_path = csv_path
        self.report_path = report_path
        self.error: str | None = None

    def write(self, result: RunnerResult) -> None:
        if self.error is not None:
            return
        if not self.csv_path and not self.report_path:
            return
        try:
            if self.csv_path:
                write_runner_events_csv(result.events, self.csv_path)
            if self.report_path:
                write_mission_report(result, self.goal, self.report_path)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"


def _reset_llm_log(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def main() -> None:
    args = parse_args()
    goal = DTGoal(
        soc_min_pct=args.soc_min,
        soc_max_pct=args.soc_max,
        bus_nominal_v=args.bus_nominal,
        success_hold_s=args.success_hold_seconds,
        max_sim_time_s=args.max_sim_seconds,
    )
    config = RunnerConfig(
        supervisor_period_s=args.tick_seconds,
        startup_grace_s=args.startup_grace_seconds,
        max_p_batt_abs_w=args.max_p_batt,
        max_p_batt_step_w=args.max_p_batt_step,
        prevent_source_backfeed=not args.allow_source_backfeed,
        source_min_power_w=args.source_min_power,
        source_power_margin_w=args.source_power_margin,
        source_power_limit_w=args.source_power_limit,
        prevent_charge_without_source_headroom=(
            not args.allow_charge_without_source_headroom
        ),
        charge_power_margin_w=args.charge_power_margin,
        charge_bus_hysteresis_v=args.charge_bus_hysteresis_volts,
        charge_recovery_hold_s=args.charge_recovery_hold_seconds,
        post_discharge_charge_hold_s=args.post_discharge_charge_hold_seconds,
        block_discharge_below_soc_min=not args.allow_discharge_below_soc_min,
        allow_source_support_below_soc_min=(
            not args.disable_source_support_below_soc_min
        ),
        source_support_entry_margin_w=max(0.0, args.source_support_entry_margin),
        source_support_clear_margin_w=max(0.0, args.source_support_clear_margin),
        source_support_bus_hysteresis_v=max(
            0.0,
            args.source_support_bus_hysteresis_volts,
        ),
        source_support_hold_s=max(0.0, args.source_support_hold_seconds),
        bus_support_min_w=max(0.0, args.bus_support_min),
        bus_support_gain_w_per_v=max(0.0, args.bus_support_gain),
        bus_support_integral_gain_w_per_v_s=max(
            0.0,
            args.bus_support_integral_gain,
        ),
        bus_support_integral_max_w=max(0.0, args.bus_support_integral_max),
        bus_support_integral_leak_per_s=max(0.0, args.bus_support_integral_leak),
        bus_support_integral_deadband_v=max(
            0.0,
            args.bus_support_integral_deadband_volts,
        ),
        bus_support_trim_gain_w_per_v_s=max(0.0, args.bus_support_trim_gain),
        bus_support_trim_max_w=max(0.0, args.bus_support_trim_max),
        bus_support_trim_decay_w_per_s=max(0.0, args.bus_support_trim_decay),
        bus_support_trim_deadband_v=max(
            0.0,
            args.bus_support_trim_deadband_volts,
        ),
        bus_support_trim_source_slack_deadband_w=max(
            0.0,
            args.bus_support_trim_source_slack_deadband,
        ),
        bus_support_target_slew_down_w_per_s=max(
            0.0,
            args.bus_support_target_slew_down,
        ),
        safety_recovery_enabled=args.safety_recovery,
        safety_recovery_attempts=max(0, args.safety_recovery_attempts),
        real_time=args.real_time,
    )
    if args.llm_log and not args.append_llm_log:
        _reset_llm_log(args.llm_log)
    policy = build_policy(args)
    if args.backend == "mock":
        print("Mock backend enabled: no Simulink or UDP communication will be used.")
    if args.backend == "simulink":
        print(
            "MATLAB Engine Simulink backend enabled: "
            "this mode does not use UDP packets. "
            f"model={args.model_path or args.model_name}"
        )
    if args.backend == "udp":
        print(
            "UDP live Simulink backend enabled: "
            f"commands={args.udp_command_host}:{args.udp_command_port}, "
            f"observations={args.udp_observation_host}:{args.udp_observation_port}"
        )
        if args.udp_republish_host and args.udp_republish_port:
            print(
                "Republishing received observations to "
                f"{args.udp_republish_host}:{args.udp_republish_port}"
            )
    if isinstance(policy, LLMControlPolicy):
        print(
            "LLM policy enabled: "
            f"model={args.llm_model}, base_url={args.llm_base_url}"
        )
        if args.llm_log:
            print(f"LLM trace log: {args.llm_log}")

    checkpointer = MissionArtifactCheckpointer(
        goal=goal,
        csv_path=args.csv,
        report_path=args.report,
    )

    def checkpoint(result: RunnerResult) -> None:
        checkpointer.write(result)
        if args.emit_gui_events:
            gui_event = format_dt_gui_event(result)
            if gui_event is not None:
                print(gui_event, flush=True)

    runner = AutonomousRunner(
        backend=build_backend(args),
        goal=goal,
        policy=policy,
        config=config,
        on_checkpoint=checkpoint,
    )
    result = runner.run()

    print(f"Mission status: {result.status.value}")
    print(f"Reason: {result.reason}")
    if result.final_observation:
        print(
            "Final observation: "
            f"t={result.final_observation.sim_time_s:.1f}s, "
            f"SOC={result.final_observation.soc_pct:.2f}%, "
            f"Vbus={result.final_observation.v_bus_v:.2f}V"
        )
    print(f"Supervisor decisions: {len(result.events)}")
    if isinstance(policy, LLMControlPolicy):
        print(
            "LLM policy calls: "
            f"attempted={policy.attempted_calls}, "
            f"successful={policy.successful_calls}, "
            f"fallbacks={policy.fallback_calls}"
        )

    if args.csv:
        write_runner_events_csv(result.events, args.csv)
        print(f"CSV log written to: {args.csv}")

    if args.report:
        write_mission_report(result, goal, args.report)
        print(f"Mission report written to: {args.report}")

    if checkpointer.error:
        print(f"Artifact checkpoint warning: {checkpointer.error}")


if __name__ == "__main__":
    main()
