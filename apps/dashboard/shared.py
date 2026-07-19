from apps.buildings.models import UserBuilding


def build_monitoring_config(building_id: int) -> dict:
    from apps.sensors.sensor_config import (
        LIMITS_EXCLUDE_VARS, PUMP_VARS, ELEVATOR_VARS, VAR_NAMES, UNITS,
        RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
        VALUE_DISPLAY_ES, ENUM_VARS, FAULT_NAMES_ES, SENSOR_RANGES, SENSOR_ABSOLUTE_RANGES
    )
    from apps.limits.services import get_sensor_limits
    from apps.buildings.models import Building
    ranges = get_sensor_limits(building_id)
    abs_ranges = {k: tuple(v) for k, v in SENSOR_ABSOLUTE_RANGES.items()}
    try:
        building = Building.objects.get(id=building_id)
        ranges["elev_position"] = (0, building.floors)
        abs_ranges["elev_position"] = (0, building.floors)
    except Building.DoesNotExist:
        pass
    return {
        "limits_exclude_vars": LIMITS_EXCLUDE_VARS,
        "pump_vars": PUMP_VARS,
        "elevator_vars": ELEVATOR_VARS,
        "var_names": VAR_NAMES,
        "units": UNITS,
        "value_display_es": VALUE_DISPLAY_ES,
        "sensor_ranges": ranges,
        "sensor_absolute_ranges": abs_ranges,
        "edificio_id": building_id,
        "enum_vars": list(ENUM_VARS),
        "risk_labels": {
            "normal": RISK_NORMAL,
            "alto": RISK_ALTO,
            "critico": RISK_CRITICO,
        },
        "fault_names_es": FAULT_NAMES_ES,
    }


def get_user_building_ids(user_id: int) -> list[int]:
    return list(UserBuilding.objects.filter(user_id=user_id).values_list("building_id", flat=True))
