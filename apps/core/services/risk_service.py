from typing import Optional

from apps.sensors.sensor_config import (
    RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
    ENUM_VARS)


def classify_risk(
    variable: str,
    value,
    thresholds: Optional[dict] = None) -> tuple[str, str]:
    """Clasifica el riesgo de un sensor según los umbrales.

    La clasificación es puramente numérica/umbral, sin lógica contextual.
    Los escenarios de falla combinada se manejan por el sistema de alertas
    compuestas (engine.py → send_compound_alert), no aquí.

    Returns:
        Tupla (nivel_riesgo, color_css): uno de
          (RISK_NORMAL, "green"), (RISK_ALTO, "orange"), (RISK_CRITICO, "red").
    """
    # Sensores de enumeración (ej: elev_door_status)
    if variable in ENUM_VARS:
        return RISK_NORMAL, "green"

    # Sin umbrales configurados → Normal por defecto
    if thresholds is None or variable not in thresholds:
        return RISK_NORMAL, "green"

    cfg = thresholds[variable]
    d = cfg["direction"]

    if d == "range":
        low  = cfg["high"]    # límite crítico inferior
        high = cfg["critic"]  # límite crítico superior
        margin = (high - low) * 0.20

        if value < low or value > high:
            return RISK_CRITICO, "red"
        if low + margin <= value <= high - margin:
            return RISK_NORMAL, "green"
        return RISK_ALTO, "orange"

    if d == "lower":
        high_thresh   = cfg["high"]
        critic_thresh = cfg["critic"]
        if value >= high_thresh:
            return RISK_NORMAL, "green"
        elif value >= critic_thresh:
            return RISK_ALTO, "orange"
        else:
            return RISK_CRITICO, "red"

    high_thresh   = cfg["high"]
    critic_thresh = cfg["critic"]
    if value <= high_thresh:
        return RISK_NORMAL, "green"
    elif value <= critic_thresh:
        return RISK_ALTO, "orange"
    else:
        return RISK_CRITICO, "red"
