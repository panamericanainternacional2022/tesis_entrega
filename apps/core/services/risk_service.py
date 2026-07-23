from typing import Optional

from apps.sensors.sensor_config import (
    RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
    ENUM_VARS, FAULT_AFFECTED_VARIABLES,
)


def classify_risk(
    variable: str,
    value,
    thresholds: Optional[dict] = None,
    is_on: Optional[bool] = None,
    active_fault: Optional[str] = None,
) -> tuple[str, str]:
    """Clasifica el riesgo de un sensor según los umbrales y el contexto operativo.

    Si existe una falla activa o el equipo está encendido (is_on=True),
    los valores anormalmente bajos (como 0 caudal o 0 corriente durante falla/operación)
    se clasifican como Crítico o Alto en lugar de Normal.

    Returns:
        Tupla (nivel_riesgo, color_css): uno de
          (RISK_NORMAL, "green"), (RISK_ALTO, "orange"), (RISK_CRITICO, "red").
    """
    # Sensores de enumeración (ej: elev_door_status)
    if variable in ENUM_VARS:
        val_str = str(value).lower()
        if val_str in ("blocked", "true"):
            return RISK_ALTO, "orange"
        if val_str == "error":
            return RISK_CRITICO, "red"
        if active_fault == "door_blocked" and val_str == "open":
            return RISK_ALTO, "orange"
        return RISK_NORMAL, "green"

    # Verificación contextual de fallas activas y estado de marcha (is_on)
    # Para sensores donde el valor 0 o muy bajo es anómalo durante falla u operación
    affected_by_fault = bool(active_fault and variable in FAULT_AFFECTED_VARIABLES.get(active_fault, []))

    if active_fault or is_on:
        try:
            num_val = float(value)
            if variable == "pump_flow_rate":
                if affected_by_fault or is_on:
                    if num_val < 1.0:
                        return RISK_CRITICO, "red"
                    elif num_val < 5.0:
                        return RISK_ALTO, "orange"
            elif variable == "pump_current":
                if affected_by_fault or is_on:
                    if num_val < 1.0:
                        return RISK_CRITICO, "red"
                    elif num_val < 5.0:
                        return RISK_ALTO, "orange"
            elif variable == "elev_speed":
                if affected_by_fault and active_fault in ("motor_stuck", "commercial_power_outage", "door_blocked", "overload"):
                    if num_val < 0.1:
                        return RISK_CRITICO, "red"
            elif variable == "elev_current":
                if affected_by_fault and active_fault == "commercial_power_outage":
                    if num_val < 1.0:
                        return RISK_CRITICO, "red"
        except (ValueError, TypeError):
            pass

    # Sin umbrales configurados -> Normal por defecto
    if thresholds is None or variable not in thresholds:
        return RISK_NORMAL, "green"

    cfg = thresholds[variable]
    d = cfg["direction"]

    if d == "range":
        low = cfg["high"]     # límite crítico inferior
        high = cfg["critic"]  # límite crítico superior
        margin = (high - low) * 0.20

        if value < low or value > high:
            return RISK_CRITICO, "red"
        if low + margin <= value <= high - margin:
            return RISK_NORMAL, "green"
        return RISK_ALTO, "orange"

    if d == "lower":
        high_thresh = cfg["high"]
        critic_thresh = cfg["critic"]
        if value >= high_thresh:
            return RISK_NORMAL, "green"
        elif value >= critic_thresh:
            return RISK_ALTO, "orange"
        else:
            return RISK_CRITICO, "red"

    high_thresh = cfg["high"]
    critic_thresh = cfg["critic"]
    if value <= high_thresh:
        return RISK_NORMAL, "green"
    elif value <= critic_thresh:
        return RISK_ALTO, "orange"
    else:
        return RISK_CRITICO, "red"

