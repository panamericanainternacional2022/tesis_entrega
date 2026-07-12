from typing import Optional

from apps.sensors.sensor_config import (
    RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
    NO_RISK_VARS, ZERO_IS_CRITICAL_VARS,
    BOOLEAN_VARS, ENUM_VARS, ENUM_RISK_VALUES,
    SENSOR_RANGES)
from apps.sensors.simulation.constants import MAX_DOOR_CLOSE_ATTEMPTS


def classify_risk(
    variable: str,
    value,
    thresholds: Optional[dict] = None,
    pump_on: bool = True,
    speed: float = 0.0,
    
    position: float = 0.0,
    load: float = 0.0,
    door_status: str = "closed",
    elevator_state: str = "IDLE",
    pos_stuck: bool = False,
    elevator_on: bool = False) -> tuple[str, str]:
    if variable in BOOLEAN_VARS:
        return (RISK_CRITICO, "red") if value else (RISK_NORMAL, "green")

    # Reglas Contextuales del Elevador — door_status
    if variable == "elev_door_status":
        str_val = str(value).lower() if value is not None else ""
        is_moving = speed > 0.05
        is_at_floor_zone = abs(position - round(position)) < 0.05

        if str_val == "closing":
            return RISK_ALTO, "orange"

        if str_val in {"open", "opening"}:
            if is_moving or not is_at_floor_zone:
                return RISK_CRITICO, "red"
            return RISK_NORMAL, "green"

        return RISK_NORMAL, "green"

    if variable == "elev_load":
        load_thresh = (thresholds or {}).get("elev_load", {})
        crit = load_thresh.get("critic", 900)
        alto = load_thresh.get("high", 600)
        if value > crit:
            return RISK_CRITICO, "red"
        elif value > alto:
            return RISK_ALTO, "orange"
        return RISK_NORMAL, "green"

    if variable == "elev_current":
        # Door blocked: forced closing consumes more current
        current_high = SENSOR_RANGES.get("elev_current", (0, 70))[1]

        # Alta corriente con velocidad cero mientras debería moverse (motor atascado)
        is_stuck_situation = elevator_state in {"ACCELERATING", "MOVING", "DECELERATING"} and speed < 0.05
        if is_stuck_situation:
            return RISK_CRITICO, "red"

        # Alto consumo en standby (IDLE) — umbral realista al 20% del máximo
        # para evitar falsos positivos por fluctuaciones normales de standby.
        if speed < 0.05 and elevator_state == "IDLE" and elevator_on:
            if value > current_high * 0.20:
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
            if value > speed_cfg.get("critic", SENSOR_RANGES.get("elev_speed", (0, 3))[1] * 0.67):
                return RISK_CRITICO, "red"
            if value > speed_cfg.get("high", SENSOR_RANGES.get("elev_speed", (0, 3))[1] * 0.42):
                return RISK_ALTO, "orange"
        else:
            speed_high = SENSOR_RANGES.get("elev_speed", (0, 3))[1]
            if value > speed_high * 0.67:
                return RISK_CRITICO, "red"
            if value > speed_high * 0.42:
                return RISK_ALTO, "orange"

    if variable == "elev_position":
        if value is None:
            return RISK_CRITICO, "red"
        # La posición no tiene umbrales de riesgo propios (simulator.md §2).
        # Solo es crítica cuando el sensor está atascado (fault: pos_sensor_fail)
        # mientras la cabina debería estar en movimiento.
        if pos_stuck and speed > 0.05:
            return RISK_CRITICO, "red"
        return RISK_NORMAL, "green"


    if variable in ENUM_VARS:
        risky_values = ENUM_RISK_VALUES.get(variable, set())
        is_risky = str(value).lower() in risky_values
        return (RISK_CRITICO, "red") if is_risky else (RISK_NORMAL, "green")

    if variable in NO_RISK_VARS:
        return RISK_NORMAL, "green"

    # Corrección para bomba apagada: flow y pressure en 0 no son anómalos
    if variable in {"pump_flow_rate", "pump_pressure"} and not pump_on:
        flow_range = SENSOR_RANGES.get("pump_flow_rate", (0, 60))
        press_range = SENSOR_RANGES.get("pump_pressure", (0, 12))
        low_val = flow_range[1] * 0.13 if variable == "pump_flow_rate" else press_range[1] * 0.17
        if thresholds and variable in thresholds:
            low_val = thresholds[variable].get("high", low_val)
        if value <= low_val:
            return RISK_NORMAL, "green"

    if variable in ZERO_IS_CRITICAL_VARS and value == 0:
        return RISK_CRITICO, "red"

    if thresholds is None or variable not in thresholds:
        return RISK_NORMAL, "green"

    cfg = thresholds[variable]
    d = cfg["direction"]

    if d == "range":
        high_bound, critic_bound = cfg["high"], cfg["critic"]
        crit_low  = cfg.get("crit_low")
        crit_high = cfg.get("crit_high")
        # Nivel Crítico bidireccional (extremos)
        if crit_low is not None and value < crit_low:
            return RISK_CRITICO, "red"
        if crit_high is not None and value > crit_high:
            return RISK_CRITICO, "red"
        # Nivel Alto (fuera del rango operativo normal)
        if high_bound <= value <= critic_bound:
            return RISK_NORMAL, "green"
        return RISK_ALTO, "orange"

    # direction == "higher": alerta cuando el valor sube
    high_thresh = cfg["high"]
    critic_thresh = cfg["critic"]
    if value <= high_thresh:
        return RISK_NORMAL, "green"
    elif value <= critic_thresh:
        return RISK_ALTO, "orange"
    else:
        return RISK_CRITICO, "red"
