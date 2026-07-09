from __future__ import annotations

from apps.sensors.sensor_config import COOLDOWN_SECONDS


def translate_variable_to_spanish(variable: str) -> str:
    from apps.sensors.sensor_config import VAR_NAMES
    return VAR_NAMES.get(variable, variable.replace("_", " ").title())
