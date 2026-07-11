from typing import Any
import logging
from dataclasses import dataclass

from apps.sensors.sensor_config import STATS_VARS, PUMP_VARS, ELEVATOR_VARS, VAR_NAMES, PAYLOAD_HISTORY_SLICE, API_HISTORY_LIMIT
from apps.sensors.simulation.constants import MAX_HISTORY_SIZE

logger = logging.getLogger(__name__)


@dataclass
class PayloadContext:
    sensor_data: dict
    history: list
    door_close_attempts: int
    pump_on: bool
    elevator_on: bool
    equipment_types: set
    sim_paused: bool
    sim_speed: float
    sim_started: bool = False
    active_edificio_id: int = None
    django_connected: bool = False
    sim_faults: dict = None
    active_alerts: dict = None


def _compute_stats(history: list, max_entries: int = MAX_HISTORY_SIZE) -> dict[str, Any]:
    stats = {}
    recent = history[-max_entries:] if len(history) > max_entries else history
    for var in STATS_VARS:
        vals = [
            r["value"]
            for r in recent
            if r["variable"] == var and isinstance(r["value"], (int, float)) and not isinstance(r["value"], bool)
        ]
        if vals:
            stats[var] = {
                "avg": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }
    return stats


def build_live_payload(ctx: PayloadContext) -> dict[str, Any]:
    from apps.thresholds.services import get_thresholds
    from apps.history.services.history_persistence import get_alert_log
    stats = _compute_stats(ctx.history)
    relevant_vars = _build_relevant_vars(ctx.equipment_types)
    thresholds = get_thresholds(ctx.active_edificio_id)
    speed = ctx.sensor_data.get("speed", 0.0)
    sensors = _build_sensors_list(
        ctx.sensor_data, relevant_vars, thresholds,
        pump_on=ctx.pump_on, speed=speed,
        door_close_attempts=ctx.door_close_attempts,
    )
    pump_status, elevator_status = _fetch_equipment_status(
        ctx.django_connected, ctx.active_edificio_id, ctx.sim_faults, ctx.active_alerts
    )
    return {
        "current": {k: v for k, v in ctx.sensor_data.items() if k in relevant_vars},
        "sensors": sensors,
        "history": [h for h in ctx.history[-PAYLOAD_HISTORY_SLICE:] if h.get("variable") in relevant_vars],
        "thresholds": thresholds,
        "alert_log": get_alert_log(ctx.active_edificio_id, API_HISTORY_LIMIT),
        "stats": stats,
        "door_close_attempts": ctx.door_close_attempts,
        "pump_on": ctx.pump_on,
        "elevator_on": ctx.elevator_on,
        "equipment_types": list(ctx.equipment_types),
        "pump_status": pump_status,
        "elevator_status": elevator_status,
        "sim_paused": ctx.sim_paused,
        "sim_speed": ctx.sim_speed,
        "sim_started": ctx.sim_started,
        "sim_faults": ctx.sim_faults or {},
    }


def _build_relevant_vars(equipment_types: set) -> set[str]:
    relevant_vars = set()
    if "bomba" in equipment_types:
        relevant_vars.update(PUMP_VARS)
    if "elevador" in equipment_types:
        relevant_vars.update(ELEVATOR_VARS)
    return relevant_vars


def _build_sensors_list(
    sensor_data: dict,
    relevant_vars: set[str],
    thresholds: dict,
    pump_on: bool = True,
    speed: float = 0.0,
    door_close_attempts: int = 0,
) -> list[dict[str, Any]]:
    from apps.core.services.risk_service import classify_risk
    sensors = []
    for var, value in sensor_data.items():
        if var not in relevant_vars:
            continue
        risk, color = classify_risk(
            var, value, thresholds,
            pump_on=pump_on, speed=speed,
            door_close_attempts=door_close_attempts,
            position=sensor_data.get("position", 0.0),
            load=sensor_data.get("load", 0.0),
            door_status=sensor_data.get("door_status", "closed"),
            elevator_state=sensor_data.get("elevator_state", "IDLE"),
        )
        sensors.append({
            "id": var,
            "nombre": VAR_NAMES.get(var, var),
            "riesgo": risk,
            "color": color,
        })
    return sensors


def _fetch_equipment_status(
    django_connected: bool,
    active_edificio_id: int,
    sim_faults: dict = None,
    active_alerts: dict = None,
) -> tuple:
    pump_status = None
    elevator_status = None
    
    has_pump_fault = False
    if sim_faults and "pump" in sim_faults:
        has_pump_fault = True
    elif active_alerts:
        if any(var in PUMP_VARS for var in active_alerts):
            has_pump_fault = True
            
    dynamic_pump = "falla" if has_pump_fault else "operativo"

    has_elev_fault = False
    if sim_faults and "elevator" in sim_faults:
        has_elev_fault = True
    elif active_alerts:
        if any(var in ELEVATOR_VARS for var in active_alerts):
            has_elev_fault = True
            
    dynamic_elev = "falla" if has_elev_fault else "operativo"

    if django_connected and active_edificio_id:
        try:
            from apps.buildings.models import MonitoringEquipment
            for eq in MonitoringEquipment.objects.filter(building_id=active_edificio_id):
                if eq.equipment_type == "bomba":
                    if eq.status != dynamic_pump:
                        eq.status = dynamic_pump
                        eq.save(update_fields=["status"])
                    pump_status = dynamic_pump
                elif eq.equipment_type == "elevador":
                    if eq.status != dynamic_elev:
                        eq.status = dynamic_elev
                        eq.save(update_fields=["status"])
                    elevator_status = dynamic_elev
        except Exception as e:
            logger.warning("Error fetching and syncing equipment status: %s", e)
            pump_status = dynamic_pump
            elevator_status = dynamic_elev
    else:
        pump_status = dynamic_pump
        elevator_status = dynamic_elev
        
    return pump_status, elevator_status



