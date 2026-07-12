import logging

from django.db import IntegrityError

from apps.sensors.sensor_config import DEFAULT_THRESHOLDS
from apps.thresholds.models import ThresholdConfig

logger = logging.getLogger(__name__)


def get_thresholds(building_id: int) -> dict:
    result = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}

    for row in ThresholdConfig.objects.filter(
        building_id=building_id
    ).values("variable", "direction", "low", "medium", "high"):
        result[row["variable"]] = {
            "direction": row["direction"],
            "low": row["low"],
            "medium": row["medium"],
            "high": row["high"],
        }

    from apps.buildings.models import Building
    building = Building.objects.filter(id=building_id).first()
    if building and building.floors > 0 and "elev_position" in result:
        result["elev_position"]["high"] = float(building.floors)

    return result


class ThresholdPersistenceError(Exception):
    pass


def update_threshold(variable: str, config: dict, building_id: int) -> None:
    medium = config.get("medium")
    if medium is not None:
        try:
            medium = float(medium)
        except (ValueError, TypeError):
            medium = None
    try:
        ThresholdConfig.objects.update_or_create(
            building_id=building_id,
            variable=variable,
            defaults={
                "direction": config.get("direction", "higher"),
                "low": config.get("low", 0),
                "medium": medium,
                "high": config.get("high", 0),
            },
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
