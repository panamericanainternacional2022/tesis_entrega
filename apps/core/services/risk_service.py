from typing import Optional

from apps.sensors.sensor_config import (
    RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
    ENUM_VARS)


def classify_risk(
    variable: str,
    value,
    thresholds: Optional[dict] = None,
    active_faults: Optional[dict] = None) -> tuple[str, str]:
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
        # Sensores con rango normal bidireccional:
        #   cfg["high"]      = límite INFERIOR del rango normal (ej: 210 V)
        #   cfg["critic"]    = límite SUPERIOR del rango normal (ej: 230 V)
        #   cfg["crit_low"]  = límite inferior crítico        (ej: 198 V)
        #   cfg["crit_high"] = límite superior crítico        (ej: 242 V)
        high_bound   = cfg["high"]
        critic_bound = cfg["critic"]
        crit_low     = cfg.get("crit_low")
        crit_high    = cfg.get("crit_high")

        # Nivel Crítico: más allá de los límites críticos
        if crit_low is not None and value < crit_low:
            return RISK_CRITICO, "red"
        if crit_high is not None and value > crit_high:
            return RISK_CRITICO, "red"
        # Nivel Normal: dentro del rango [high, critic]
        if high_bound <= value <= critic_bound:
            return RISK_NORMAL, "green"
        # Nivel Alto: fuera del rango normal, pero dentro del crítico
        return RISK_ALTO, "orange"

    # direction == "higher": alerta cuando el valor sube
    #   cfg["high"]   = umbral entre Normal y Alto
    #   cfg["critic"] = umbral entre Alto y Crítico
    high_thresh   = cfg["high"]
    critic_thresh = cfg["critic"]
    if value <= high_thresh:
        return RISK_NORMAL, "green"
    elif value <= critic_thresh:
        return RISK_ALTO, "orange"
    else:
        return RISK_CRITICO, "red"
