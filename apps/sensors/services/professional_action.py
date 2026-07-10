from typing import Any

from apps.sensors.sensor_config import (
    VAR_NAMES, ACTIONS,
    FALLBACK_ACTION_TEMPLATE,
)


def get_professional_action(variable: str, risk_level: str, value: Any) -> str:
    var_actions = ACTIONS.get(variable, {})
    var_display = VAR_NAMES.get(variable, variable.replace("_", " "))
    return var_actions.get(risk_level, FALLBACK_ACTION_TEMPLATE.format(var_display.lower()))
