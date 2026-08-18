from typing import Dict, Optional


DEFAULT_DT_STATE = {
    "es_dt": {"status": "deactivate"},
    "ell_dt": {"status": "deactivate"},
    "elh_dt": {"status": "deactivate"},
    "th_dt": {"status": "deactivate"},
}


class DTStateManager:
    def __init__(self, initial_state: Optional[Dict[str, Dict[str, str]]] = None):
        source_state = initial_state or DEFAULT_DT_STATE
        self.dt_data = {
            name.lower(): {"status": state.get("status", "deactivate").lower()}
            for name, state in source_state.items()
        }

    def get_DT_state(
        self,
        dt_name: Optional[str] = None,
        DT: Optional[str] = None,
    ) -> dict:
        key = self._normalize_name(dt_name or DT)
        if not key:
            return {"error": "A digital twin name is required."}

        result = self.dt_data.get(key)
        if result is None:
            return {"error": f"Unknown DT: {key}"}

        return {"dt_name": key, "status": result["status"]}

    def set_DT_state(
        self,
        dt_name: Optional[str] = None,
        state: Optional[str] = None,
        DT: Optional[str] = None,
        Setting: Optional[str] = None,
    ) -> dict:
        key = self._normalize_name(dt_name or DT)
        desired_state = (state or Setting or "").strip().lower()

        if not key:
            return {"error": "A digital twin name is required."}
        if key not in self.dt_data:
            return {"error": f"Unknown DT: {key}"}
        if desired_state not in {"activate", "deactivate"}:
            return {"error": f"Invalid state: {desired_state or state}"}

        self.dt_data[key]["status"] = desired_state
        return {"dt_name": key, "status": desired_state}

    @staticmethod
    def _normalize_name(value: Optional[str]) -> str:
        return (value or "").strip().lower()
