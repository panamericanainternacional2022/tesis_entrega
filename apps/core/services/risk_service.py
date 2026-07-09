from typing import Optional

from apps.sensors.sensor_config import (
    RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
    NO_RISK_VARS, RISK_UNKNOWN, ZERO_IS_CRITICAL_VARS,
    BOOLEAN_VARS, ENUM_VARS, ENUM_RISK_VALUES,
    SENSOR_RANGES,
)


def classify_risk(
    variable: str,
    value,
    thresholds: Optional[dict] = None,
    pump_on: bool = True,
    speed: float = 0.0,
    door_close_attempts: int = 0,
    position: float = 0.0,
    load: float = 0.0,
    door_status: str = "closed",
    elevator_state: str = "IDLE",
    pos_stuck: bool = False,
    elevator_on: bool = False,
) -> tuple[str, str]:
    if variable in BOOLEAN_VARS:
        return (RISK_CRITICO, "red") if value else (RISK_NORMAL, "green")

    # Reglas Contextuales del Elevador
    if variable == "door_status":
        is_open = str(value).lower() in {"open", "opening", "closing"}
        is_moving = speed > 0.05
        is_at_floor_zone = abs(position - round(position)) < 0.05
        
        if is_open:
            if is_moving or not is_at_floor_zone:
                return RISK_CRITICO, "red"
            if str(value).lower() == "closing":
                if door_close_attempts >= 2:
                    return RISK_CRITICO, "red"
                return RISK_ALTO, "orange"
            if door_close_attempts >= 2:
                return RISK_ALTO, "orange"
        return RISK_NORMAL, "green"

    if variable == "load":
        load_thresh = (thresholds or {}).get("load", {})
        crit = load_thresh.get("high", 900)
        alto = load_thresh.get("low", 600)
        if value > crit:
            return RISK_CRITICO, "red"
        elif value > alto:
            return RISK_ALTO, "orange"
        return RISK_NORMAL, "green"

    if variable in {"energy", "elev_current", "current"}:
        # Energy = 0 during operation = critical (power outage)
        if variable == "energy" and value == 0 and elevator_on:
            return RISK_CRITICO, "red"

        # Door blocked: forced closing consumes more energy
        energy_high = SENSOR_RANGES.get("energy", (0, 20))[1]
        if variable == "energy" and door_status == "closing" and door_close_attempts >= 1 and value > energy_high * 0.05:
            return RISK_ALTO, "orange"

        # Alta corriente/energía con velocidad cero mientras debería moverse (motor atascado)
        is_stuck_situation = elevator_state in {"ACCELERATING", "MOVING", "DECELERATING"} and speed < 0.05
        if is_stuck_situation:
            return RISK_CRITICO, "red"

        # Alto consumo en standby (IDLE)
        if speed < 0.05 and elevator_state == "IDLE":
            if variable == "energy" and value > energy_high * 0.1:
                return RISK_CRITICO, "red"
            current_range = SENSOR_RANGES.get("current", (0, 70))
            if variable in {"elev_current", "current"} and value > current_range[1] * 0.07:
                return RISK_CRITICO, "red"

    if variable == "speed":
        if elevator_state in {"ACCELERATING", "MOVING", "DECELERATING"} and value < 0.05:
            return RISK_CRITICO, "red"
        if value > 0.05 and door_status != "closed":
            return RISK_CRITICO, "red"
        speed_cfg = (thresholds or {}).get("speed", {})
        if speed_cfg:
            if value > speed_cfg.get("high", SENSOR_RANGES.get("speed", (0, 6))[1] * 0.67):
                return RISK_CRITICO, "red"
            if value > speed_cfg.get("low", SENSOR_RANGES.get("speed", (0, 6))[1] * 0.42):
                return RISK_ALTO, "orange"
        else:
            speed_high = SENSOR_RANGES.get("speed", (0, 6))[1]
            if value > speed_high * 0.67:
                return RISK_CRITICO, "red"
            if value > speed_high * 0.42:
                return RISK_ALTO, "orange"

    if variable == "position":
        if value is None:
            return RISK_CRITICO, "red"
        if abs(value - round(value)) > 0.05:
            return RISK_CRITICO, "red"
        if pos_stuck and speed > 0.05:
            return RISK_CRITICO, "red"

    if variable == "door_close_attempts":
        if value >= 2:
            return RISK_ALTO, "orange"
        return RISK_NORMAL, "green"

    if variable == "trip_count":
        return RISK_NORMAL, "green"

    if variable in ENUM_VARS:
        risky_values = ENUM_RISK_VALUES.get(variable, set())
        is_risky = str(value).lower() in risky_values
        return (RISK_CRITICO, "red") if is_risky else (RISK_NORMAL, "green")

    if variable in NO_RISK_VARS:
        return RISK_NORMAL, "green"

    # Corrección para bomba apagada
    if variable in {"flow_rate", "pressure"} and not pump_on:
        flow_range = SENSOR_RANGES.get("flow_rate", (0, 60))
        press_range = SENSOR_RANGES.get("pressure", (0, 12))
        low_val = flow_range[1] * 0.13 if variable == "flow_rate" else press_range[1] * 0.17
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
