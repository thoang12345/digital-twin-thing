from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from Modules.Digital_Twins.types import DTCommand, DTObservation


class SimulationBackend(Protocol):
    """Interface between the autonomous runner and a DT simulation."""

    def reset(self) -> DTObservation:
        """Reset or initialize the simulation and return the first observation."""

    def observe(self) -> DTObservation:
        """Return the latest state snapshot."""

    def apply_command(self, command: DTCommand) -> None:
        """Apply a command that will be held until the next supervisor tick."""

    def advance(self, seconds: float) -> DTObservation:
        """Advance the simulation by the requested simulated time."""

    def close(self) -> None:
        """Release backend resources."""


@dataclass(slots=True)
class MockBatteryBusBackend:
    """Small deterministic stand-in for the Simulink battery/load-bus model.

    The sign convention matches the battery-power command interface:

    - positive ``P_batt_cmd`` requests battery discharge into the bus
    - negative ``P_batt_cmd`` requests battery charging from the bus/source

    This is not a physics replacement for Simulink. It exists so the runner,
    policy, safety checks, and logs can be tested before the Simulink bridge is
    wired.
    """

    initial_soc_pct: float = 55.0
    bus_nominal_v: float = 400.0
    battery_capacity_wh: float = 2_000.0
    load_power_w: float = 2_500.0
    source_power_limit_w: float = 3_000.0
    source_available: bool = True
    max_charge_power_w: float = 2_000.0
    max_discharge_power_w: float = 2_000.0
    _time_s: float = field(init=False, repr=False)
    _soc_pct: float = field(init=False, repr=False)
    _command: DTCommand = field(init=False, repr=False)
    _observation: DTObservation = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._time_s = 0.0
        self._soc_pct = self.initial_soc_pct
        self._command = DTCommand.hold("initial command")
        self._observation = self._make_observation(
            p_batt_w=0.0,
            p_source_w=min(self.load_power_w, self.source_power_limit_w),
            source_at_limit=self.load_power_w >= self.source_power_limit_w,
        )

    def reset(self) -> DTObservation:
        self._time_s = 0.0
        self._soc_pct = self.initial_soc_pct
        self._command = DTCommand.hold("reset")
        self._observation = self._make_observation(
            p_batt_w=0.0,
            p_source_w=min(self.load_power_w, self.source_power_limit_w),
            source_at_limit=self.load_power_w >= self.source_power_limit_w,
        )
        return self._observation

    def observe(self) -> DTObservation:
        return self._observation

    def apply_command(self, command: DTCommand) -> None:
        self._command = command

    def advance(self, seconds: float) -> DTObservation:
        if seconds <= 0:
            raise ValueError("advance seconds must be positive")

        requested_p_batt_w = self._command.p_batt_cmd_w if self._command.enable else 0.0

        p_batt_w = min(
            self.max_discharge_power_w,
            max(-self.max_charge_power_w, requested_p_batt_w),
        )

        if self._soc_pct <= 0.0 and p_batt_w > 0.0:
            p_batt_w = 0.0
        if self._soc_pct >= 100.0 and p_batt_w < 0.0:
            p_batt_w = 0.0

        source_required_w = self.load_power_w - p_batt_w
        source_limit_w = self.source_power_limit_w if self.source_available else 0.0
        p_source_w = min(max(source_required_w, 0.0), source_limit_w)
        source_at_limit = source_required_w >= source_limit_w and source_limit_w > 0.0

        deficit_w = max(0.0, source_required_w - p_source_w)
        if deficit_w > 0.0:
            sag_fraction = min(0.45, deficit_w / max(self.load_power_w, 1.0) * 0.25)
            v_bus_v = self.bus_nominal_v * (1.0 - sag_fraction)
        else:
            v_bus_v = self.bus_nominal_v

        delta_soc_pct = -(p_batt_w * seconds / 3600.0) / self.battery_capacity_wh * 100.0
        self._soc_pct = min(100.0, max(0.0, self._soc_pct + delta_soc_pct))
        self._time_s += seconds

        self._observation = self._make_observation(
            p_batt_w=p_batt_w,
            p_source_w=p_source_w,
            source_at_limit=source_at_limit,
            v_bus_v=v_bus_v,
        )
        return self._observation

    def close(self) -> None:
        return None

    def _make_observation(
        self,
        p_batt_w: float,
        p_source_w: float,
        source_at_limit: bool,
        v_bus_v: float | None = None,
    ) -> DTObservation:
        v_batt_v = 300.0 + (self._soc_pct - 50.0) * 0.6
        i_batt_a = p_batt_w / v_batt_v if v_batt_v else 0.0
        return DTObservation(
            sim_time_s=self._time_s,
            soc_pct=self._soc_pct,
            v_bus_v=v_bus_v if v_bus_v is not None else self.bus_nominal_v,
            v_batt_v=v_batt_v,
            i_batt_a=i_batt_a,
            p_batt_w=p_batt_w,
            p_load_w=self.load_power_w,
            load_consumption_w=self.load_power_w,
            p_source_w=p_source_w,
            source_power_limit_w=self.source_power_limit_w,
            source_can_sink_power=False,
            source_at_limit=source_at_limit,
            source_available=self.source_available,
            extra={
                "command_mode": self._command.mode,
                "command_p_batt_cmd_w": self._command.p_batt_cmd_w,
            },
        )


@dataclass(slots=True)
class SimulinkBackend:
    """MATLAB Engine bridge for the live Simulink model.

    The bridge expects the Simulink model to expose command variables and logged
    state signals:

    - command variables: ``P_batt_cmd``, ``enable_cmd``, ``mode_cmd``
    - a logged ``dt_state`` bus, or individually logged signals such as
      ``soc_pct``, ``v_bus_v``, ``i_batt_a``, and ``p_source_w``

    MATLAB is imported lazily so the mock backend and unit tests still run on
    machines that do not have MATLAB Engine for Python installed.
    """

    model_name: str = "DT_enviroment"
    model_path: str | Path | None = None
    bridge_dir: str | Path | None = None
    p_batt_cmd_variable: str = "P_batt_cmd"
    enable_variable: str = "enable_cmd"
    mode_variable: str = "mode_cmd"
    matlab_engine: Any | None = field(default=None, repr=False)
    close_engine_on_exit: bool = True
    _engine: Any | None = field(init=False, default=None, repr=False)
    _engine_owned: bool = field(init=False, default=False, repr=False)
    _latest_observation: DTObservation | None = field(
        init=False, default=None, repr=False
    )
    _last_command: DTCommand = field(init=False, repr=False)

    def __post_init__(self) -> None:
        module_dir = Path(__file__).resolve().parent
        self._engine = None
        self._engine_owned = False
        self._latest_observation = None
        if self.bridge_dir is None:
            self.bridge_dir = module_dir / "matlab_bridge"
        if self.model_path is None:
            default_model = module_dir / f"{self.model_name}.slx"
            self.model_path = default_model if default_model.exists() else ""
        self._last_command = DTCommand.hold("initial command")

    def reset(self) -> DTObservation:
        engine = self._ensure_engine()
        observation_json = engine.dt_bridge_init(
            self.model_name,
            self._model_path_string(),
            self.p_batt_cmd_variable,
            self.enable_variable,
            self.mode_variable,
            nargout=1,
        )
        self._latest_observation = self._observation_from_json(observation_json)
        return self._latest_observation

    def observe(self) -> DTObservation:
        if self._latest_observation is not None:
            return self._latest_observation
        engine = self._ensure_engine()
        observation_json = engine.dt_bridge_observe(nargout=1)
        self._latest_observation = self._observation_from_json(observation_json)
        return self._latest_observation

    def apply_command(self, command: DTCommand) -> None:
        engine = self._ensure_engine()
        self._last_command = command
        engine.dt_bridge_apply_command(
            float(command.p_batt_cmd_w),
            float(1.0 if command.enable else 0.0),
            command.mode,
            command.reason,
            nargout=0,
        )

    def advance(self, seconds: float) -> DTObservation:
        if seconds <= 0:
            raise ValueError("advance seconds must be positive")
        engine = self._ensure_engine()
        observation_json = engine.dt_bridge_step(float(seconds), nargout=1)
        self._latest_observation = self._observation_from_json(observation_json)
        return self._latest_observation

    def close(self) -> None:
        if self._engine is None:
            return
        try:
            self._engine.dt_bridge_close(nargout=0)
        finally:
            if self._engine_owned and self.close_engine_on_exit:
                self._engine.quit()
            self._engine = None
            self._engine_owned = False

    def _ensure_engine(self):
        if self._engine is not None:
            return self._engine

        if self.matlab_engine is not None:
            self._engine = self.matlab_engine
            self._engine_owned = False
        else:
            try:
                import matlab.engine  # type: ignore[import-not-found]
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "MATLAB Engine for Python is not installed in this Python "
                    "environment. Install/configure MATLAB Engine, or use "
                    "--backend mock while wiring the Simulink model."
                ) from exc
            self._engine = matlab.engine.start_matlab()
            self._engine_owned = True

        bridge_path = str(Path(self.bridge_dir).expanduser().resolve())
        self._engine.addpath(bridge_path, nargout=0)

        model_path = self._model_path_string()
        if model_path:
            self._engine.addpath(str(Path(model_path).parent), nargout=0)

        return self._engine

    def _model_path_string(self) -> str:
        if not self.model_path:
            return ""
        return str(Path(self.model_path).expanduser().resolve())

    @staticmethod
    def _observation_from_json(observation_json: Any) -> DTObservation:
        payload = json.loads(str(observation_json))
        if not isinstance(payload, dict):
            raise RuntimeError("Simulink bridge returned a non-object observation")

        fault_flags = payload.get("fault_flags")
        if not isinstance(fault_flags, dict):
            fault_flags = {}

        extra = payload.get("extra")
        if not isinstance(extra, dict):
            extra = {}

        return DTObservation(
            sim_time_s=_float_payload(payload, "sim_time_s", 0.0),
            soc_pct=_float_payload(payload, "soc_pct", 0.0),
            v_bus_v=_float_payload(payload, "v_bus_v", 0.0),
            v_batt_v=_float_payload(payload, "v_batt_v", 0.0),
            i_batt_a=_float_payload(payload, "i_batt_a", 0.0),
            p_batt_w=_float_payload(payload, "p_batt_w", 0.0),
            p_load_w=_float_payload(payload, "p_load_w", 0.0),
            load_consumption_w=_optional_float_payload(
                payload, "load_consumption_w"
            ),
            p_source_w=_float_payload(payload, "p_source_w", 0.0),
            max_safe_discharge_w=_optional_float_payload(
                payload, "max_safe_discharge_w"
            ),
            max_safe_charge_w=_optional_float_payload(payload, "max_safe_charge_w"),
            source_power_limit_w=_optional_float_payload(
                payload, "source_power_limit_w"
            ),
            source_can_sink_power=_bool_payload(
                payload, "source_can_sink_power", False
            ),
            source_at_limit=_bool_payload(payload, "source_at_limit", False),
            source_available=_bool_payload(payload, "source_available", True),
            fault_flags={
                str(name): _coerce_bool(value)
                for name, value in fault_flags.items()
            },
            extra=dict(extra),
        )


def _float_payload(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    if isinstance(value, list):
        value = value[-1] if value else default
    if value is None:
        return default
    return float(value)


def _optional_float_payload(payload: dict[str, Any], key: str) -> float | None:
    if key not in payload:
        return None
    value = payload.get(key)
    if isinstance(value, list):
        value = value[-1] if value else None
    if value is None:
        return None
    resolved = float(value)
    if not math.isfinite(resolved):
        return None
    return resolved


def _bool_payload(payload: dict[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    return _coerce_bool(value)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, list):
        value = value[-1] if value else False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
