from typing import Optional

from apps.sensors.sensor_config import (
    RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
    NO_RISK_VARS, RISK_UNKNOWN, ZERO_IS_CRITICAL_VARS,
    BOOLEAN_VARS, ENUM_VARS, ENUM_RISK_VALUES,
)


def classify_risk(
    variable: str,
    value,
    thresholds: Optional[dict] = None,
    pump_on: bool = True,
    speed: float = 0.0,
    door_close_attempts: int = 0,
) -> tuple[str, str]:
    if variable in BOOLEAN_VARS:
        return (RISK_CRITICO, "red") if value else (RISK_NORMAL, "green")
    if variable in ENUM_VARS:
        risky_values = ENUM_RISK_VALUES.get(variable, set())
        is_risky = str(value).lower() in risky_values
        if variable == "door_status" and is_risky:
            # Door is open. It is normal if speed <= 0.05 and close attempts < 2
            is_moving = speed > 0.05
            has_failed_to_close = door_close_attempts >= 2
            if not is_moving and not has_failed_to_close:
                return RISK_NORMAL, "green"
        return (RISK_CRITICO, "red") if is_risky else (RISK_NORMAL, "green")
    if variable in NO_RISK_VARS:
        return RISK_NORMAL, "green"

    # Pump idle sensor correction: if pump is off, low flow and pressure are normal
    if variable in {"flow_rate", "pressure"} and not pump_on:
        low_val = 8.0 if variable == "flow_rate" else 2.0
        if thresholds and variable in thresholds:
            low_val = thresholds[variable].get("low", low_val)
        if value <= low_val:
            return RISK_NORMAL, "green"

    if variable in ZERO_IS_CRITICAL_VARS and value == 0:
        return RISK_CRITICO, "red"
    if thresholds is None or variable not in thresholds:
        return RISK_UNKNOWN, "gray"
    cfg = thresholds[variable]
    d = cfg["direction"]
    if d == "range":
        low, high = cfg["low"], cfg["high"]
        return (RISK_NORMAL, "green") if low <= value <= high else (RISK_ALTO, "orange")
    else:
        low, med, high = cfg["low"], cfg["medium"], cfg["high"]
        if d == "higher":
            if value <= low:
                return RISK_NORMAL, "green"
            elif value <= high:
                return RISK_ALTO, "orange"
            else:
                return RISK_CRITICO, "red"
        else:
            if value >= low:
                return RISK_NORMAL, "green"
            elif value >= high:
                return RISK_ALTO, "orange"
            else:
                return RISK_CRITICO, "red"
