from typing import Optional

from apps.sensors.sensor_config import (
    RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
    NO_RISK_VARS, ZERO_IS_CRITICAL_VARS,
    BOOLEAN_VARS, ENUM_VARS, ENUM_RISK_VALUES,
    SENSOR_RANGES,
)
from apps.sensors.simulation.constants import MAX_DOOR_CLOSE_ATTEMPTS


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

    # Reglas Contextuales del Elevador — door_status
    if variable == "elev_door_status":
        str_val = str(value).lower() if value is not None else ""
        is_moving = speed > 0.05
        is_at_floor_zone = abs(position - round(position)) < 0.05

        if str_val == "closing":
            if door_close_attempts >= 2:
                return RISK_CRITICO, "red"
            return RISK_ALTO, "orange"

        if str_val in {"open", "opening"}:
            if is_moving or not is_at_floor_zone:
                return RISK_CRITICO, "red"
            if door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
                return RISK_CRITICO, "red"
            if door_close_attempts >= 2:
                return RISK_ALTO, "orange"
            return RISK_NORMAL, "green"

        return RISK_NORMAL, "green"

    if variable == "elev_load":
        load_thresh = (thresholds or {}).get("elev_load", {})
        crit = load_thresh.get("high", 900)
        alto = load_thresh.get("low", 600)
        if value > crit:
            return RISK_CRITICO, "red"
        elif value > alto:
            return RISK_ALTO, "orange"
        return RISK_NORMAL, "green"

    if variable == "elev_current":
        # Door blocked: forced closing consumes more current
        current_high = SENSOR_RANGES.get("elev_current", (0, 70))[1]
        if door_status == "closing" and door_close_attempts >= 1 and value > current_high * 0.07:
            return RISK_ALTO, "orange"

        # Alta corriente con velocidad cero mientras debería moverse (motor atascado)
        is_stuck_situation = elevator_state in {"ACCELERATING", "MOVING", "DECELERATING"} and speed < 0.05
        if is_stuck_situation:
            return RISK_CRITICO, "red"

        # Alto consumo en standby (IDLE)
        if speed < 0.05 and elevator_state == "IDLE":
            if value > current_high * 0.07:
                return RISK_CRITICO, "red"

    if variable == "elev_temperature":
        # Motor stuck or overspeed → high temperature = critical
        is_stuck_situation = elevator_state in {"ACCELERATING", "MOVING", "DECELERATING"} and speed < 0.05
        if is_stuck_situation:
            return RISK_CRITICO, "red"

        # High temperature in any state = critical
        temp_high = SENSOR_RANGES.get("elev_temperature", (25, 130))[1]
        if value > temp_high * 0.8:
            return RISK_CRITICO, "red"
        if value > temp_high * 0.6:
            return RISK_ALTO, "orange"

    if variable == "elev_speed":
        if elevator_state in {"ACCELERATING", "MOVING", "DECELERATING"} and value < 0.05:
            return RISK_CRITICO, "red"
        if value > 0.05 and door_status != "closed":
            return RISK_CRITICO, "red"
        speed_cfg = (thresholds or {}).get("elev_speed", {})
        if speed_cfg:
            if value > speed_cfg.get("high", SENSOR_RANGES.get("elev_speed", (0, 6))[1] * 0.67):
                return RISK_CRITICO, "red"
            if value > speed_cfg.get("low", SENSOR_RANGES.get("elev_speed", (0, 6))[1] * 0.42):
                return RISK_ALTO, "orange"
        else:
            speed_high = SENSOR_RANGES.get("elev_speed", (0, 6))[1]
            if value > speed_high * 0.67:
                return RISK_CRITICO, "red"
            if value > speed_high * 0.42:
                return RISK_ALTO, "orange"

    if variable == "elev_position":
        if value is None:
            return RISK_CRITICO, "red"
        if abs(value - round(value)) > 0.05:
            return RISK_CRITICO, "red"
        if pos_stuck and speed > 0.05:
            return RISK_CRITICO, "red"

    if variable == "elev_door_close_attempts":
        if value >= 2:
            return RISK_ALTO, "orange"
        return RISK_NORMAL, "green"

    if variable in ENUM_VARS:
        risky_values = ENUM_RISK_VALUES.get(variable, set())
        is_risky = str(value).lower() in risky_values
        return (RISK_CRITICO, "red") if is_risky else (RISK_NORMAL, "green")

    if variable in NO_RISK_VARS:
        return RISK_NORMAL, "green"

    # Corrección para bomba apagada
    if variable in {"pump_flow_rate", "pump_pressure"} and not pump_on:
        flow_range = SENSOR_RANGES.get("pump_flow_rate", (0, 60))
        press_range = SENSOR_RANGES.get("pump_pressure", (0, 12))
        low_val = flow_range[1] * 0.13 if variable == "pump_flow_rate" else press_range[1] * 0.17
        if thresholds and variable in thresholds:
            low_val = thresholds[variable].get("low", low_val)
        if value <= low_val:
            return RISK_NORMAL, "green"

    if variable in ZERO_IS_CRITICAL_VARS and value == 0:
        return RISK_CRITICO, "red"

    if thresholds is None or variable not in thresholds:
        return RISK_NORMAL, "green"

    cfg = thresholds[variable]
    d = cfg["direction"]
    if d == "range":
        low, high = cfg["low"], cfg["high"]
        return (RISK_NORMAL, "green") if low <= value <= high else (RISK_ALTO, "orange")
    else:
        low, _, high = cfg["low"], cfg["medium"], cfg["high"]
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
