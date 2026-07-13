import logging

from django.db import IntegrityError

from apps.limits.models import SensorLimitConfig
from apps.sensors.sensor_config import SENSOR_RANGES

logger = logging.getLogger(__name__)


def get_sensor_limits(building_id: int) -> dict[str, tuple[float, float]]:
    result: dict[str, tuple[float, float]] = {k: tuple(v) for k, v in SENSOR_RANGES.items()}
    try:
        for row in SensorLimitConfig.objects.filter(building_id=building_id):
            default_min = SENSOR_RANGES.get(row.variable, (0.0, 100.0))[0]
            result[row.variable] = (default_min, row.max_value)
    except Exception as e:
        logger.debug("Could not load sensor limits from DB (building %s): %s", building_id, e)
    return result


class LimitPersistenceError(Exception):
    pass


def _update_sensor_limit(variable: str, max_value: float, building_id: int) -> None:
    try:
        SensorLimitConfig.objects.update_or_create(
            building_id=building_id,
            variable=variable,
            defaults={
                "max_value": float(max_value),
            },
        )
        from apps.sensors.simulation.globals import simulators
        if building_id in simulators:
            simulators[building_id].refresh_limits()
    except IntegrityError:
        raise LimitPersistenceError(f"Could not persist limit {variable}: integrity error")
    except Exception as e:
        raise LimitPersistenceError(f"Could not persist limit {variable}: {e}")


def bulk_update_limits(limits_dict: dict[str, float], building_id: int) -> None:
    errors: list[str] = []
    for var, max_val in limits_dict.items():
        try:
            _update_sensor_limit(var, max_val, building_id)
        except LimitPersistenceError as e:
            errors.append(str(e))
    if errors:
        raise LimitPersistenceError("; ".join(errors))
