import logging

from django.db import IntegrityError

from apps.sensors.sensor_config import DEFAULT_THRESHOLDS
from apps.thresholds.models import ThresholdConfig

logger = logging.getLogger(__name__)


def get_thresholds(building_id: int) -> dict:
    result = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}

    for row in ThresholdConfig.objects.filter(
        building_id=building_id
    ).values("variable", "direction", "high", "critic"):
        result[row["variable"]] = {
            "direction": row["direction"],
            "high": row["high"],
            "critic": row["critic"],
        }
    return result


class ThresholdPersistenceError(Exception):
    pass


def update_threshold(variable: str, config: dict, building_id: int) -> None:
    try:
        defaults = {
            "direction": config.get("direction", "higher"),
            "high": config.get("high", 0),
            "critic": config.get("critic", 0),
        }
        ThresholdConfig.objects.update_or_create(
            building_id=building_id,
            variable=variable,
            defaults=defaults,
        )
    except IntegrityError:
        raise ThresholdPersistenceError(f"Could not persist threshold {variable}: integrity error")


def bulk_update(thresholds_dict: dict, building_id: int) -> None:
    errors: list[str] = []
    for var, config in thresholds_dict.items():
        try:
            update_threshold(var, config, building_id)
        except ThresholdPersistenceError as e:
            errors.append(str(e))
    if errors:
        raise ThresholdPersistenceError("; ".join(errors))

