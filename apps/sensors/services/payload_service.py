from typing import Any
import logging
import math
import time
from dataclasses import dataclass

from apps.sensors.sensor_config import STATS_VARS, PUMP_VARS, ELEVATOR_VARS, PAYLOAD_HISTORY_SLICE, API_HISTORY_LIMIT
from apps.sensors.simulation.constants import MAX_HISTORY_SIZE

logger = logging.getLogger(__name__)

_EQUIPMENT_SYNC_INTERVAL = 5
_ALERT_LOG_CACHE_TTL = 3


@dataclass
class PayloadContext:
    sensor_data: dict
    history: list

    pump_on: bool
    elevator_on: bool
    equipment_types: set
    sim_paused: bool
    sim_speed: float
    sim_started: bool = False
    active_edificio_id: int = None
    django_connected: bool = False
    sim_faults: dict = None

    elev_state: str = None
    elev_target_floor: int = None
    elev_direction: int = None
    pump_demand: float = None
    fault_injected_at: dict = None
    fault_transition_pump: str = "stable"
    fault_transition_elev: str = "stable"


def _compute_stats(history: list, max_entries: int = MAX_HISTORY_SIZE) -> dict[str, Any]:
    stats = {}
    recent = history[-max_entries:] if len(history) > max_entries else history
    for var in STATS_VARS:
        vals = [
            r["value"]
            for r in recent
            if r["variable"] and r["variable"] == var and isinstance(r["value"], (int, float)) and not isinstance(r["value"], bool)
        ]
        if vals:
            avg = sum(vals) / len(vals)
            std = math.sqrt(sum((v - avg) ** 2 for v in vals) / len(vals)) if len(vals) > 1 else 0.0
            stats[var] = {
                "avg": avg,
                "min": min(vals),
                "max": max(vals),
                "std": std,
            }
    return stats


def build_live_payload(ctx: PayloadContext) -> dict[str, Any]:
    from apps.thresholds.services import get_thresholds
    from apps.core.services.risk_service import classify_risk
    stats = _compute_stats(ctx.history)
    relevant_vars = _build_relevant_vars(ctx.equipment_types)
    thresholds = get_thresholds(ctx.active_edificio_id)
    _maybe_sync_equipment_status(
        ctx.django_connected, ctx.active_edificio_id, ctx.sim_faults
    )
    alert_log = _get_alert_log_cached(ctx.active_edificio_id)
    latest_ts = ctx.history[-1]["timestamp"] if ctx.history else None

    current = {k: v for k, v in ctx.sensor_data.items() if k in relevant_vars}

    _BADGE_MAP = {"Normal": "badge-normal", "Alto": "badge-high", "Crítico": "badge-crit"}
    risk = {}
    for var, val in current.items():
        level, _color = classify_risk(var, val, thresholds)
        risk[var] = {"label": level, "badge": _BADGE_MAP.get(level, "badge-normal")}

    return {
        "current": current,
        "risk": risk,
        "history": [h for h in ctx.history[-PAYLOAD_HISTORY_SLICE:] if h.get("variable") in relevant_vars],
        "thresholds": thresholds,
        "alert_log": alert_log,
        "stats": stats,
        "stats_timestamp": latest_ts,

        "pump_on": ctx.pump_on,
        "elevator_on": ctx.elevator_on,
        "equipment_types": list(ctx.equipment_types),
        "sim_paused": ctx.sim_paused,
        "sim_speed": ctx.sim_speed,
        "sim_started": ctx.sim_started,
        "sim_faults": ctx.sim_faults or {},

        "elev_state": ctx.elev_state,
        "elev_target_floor": ctx.elev_target_floor,
        "elev_direction": ctx.elev_direction,
        "pump_demand": ctx.pump_demand,
        "fault_injected_at": ctx.fault_injected_at or {},
        "fault_transition": {
            "pump": ctx.fault_transition_pump,
            "elevator": ctx.fault_transition_elev,
        },
    }


def _build_relevant_vars(equipment_types: set) -> set[str]:
    relevant_vars = set()
    if "bomba" in equipment_types:
        relevant_vars.update(PUMP_VARS)
    if "elevador" in equipment_types:
        relevant_vars.update(ELEVATOR_VARS)
    return relevant_vars


def _get_alert_log_cached(edificio_id: int) -> list:
    from django.core.cache import cache
    cache_key = f"alert_log_{edificio_id}"
    result = cache.get(cache_key)
    if result is None:
        from apps.history.services.history_persistence import get_alert_log
        result = get_alert_log(edificio_id, API_HISTORY_LIMIT)
        cache.set(cache_key, result, timeout=_ALERT_LOG_CACHE_TTL)
    return result


def _maybe_sync_equipment_status(
    django_connected: bool,
    active_edificio_id: int,
    sim_faults: dict = None,
) -> None:
    if not django_connected or not active_edificio_id:
        return
    from django.core.cache import cache
    cache_key = f"eq_sync_{active_edificio_id}"
    last_sync = cache.get(cache_key, 0)
    now = time.time()
    if now - last_sync < _EQUIPMENT_SYNC_INTERVAL:
        return
    cache.set(cache_key, now, timeout=_EQUIPMENT_SYNC_INTERVAL + 5)
    _sync_equipment_status(django_connected, active_edificio_id, sim_faults)


def _sync_equipment_status(
    django_connected: bool,
    active_edificio_id: int,
    sim_faults: dict = None) -> None:
    has_pump_fault = bool(sim_faults and "pump" in sim_faults)
    dynamic_pump = "falla" if has_pump_fault else "operativo"

    has_elev_fault = bool(sim_faults and "elevator" in sim_faults)
    dynamic_elev = "falla" if has_elev_fault else "operativo"

    if django_connected and active_edificio_id:
        try:
            from apps.buildings.models import MonitoringEquipment
            for eq in MonitoringEquipment.objects.filter(building_id=active_edificio_id):
                if eq.equipment_type == "bomba":
                    if eq.status != dynamic_pump:
                        eq.status = dynamic_pump
                        eq.save(update_fields=["status"])
                elif eq.equipment_type == "elevador":
                    if eq.status != dynamic_elev:
                        eq.status = dynamic_elev
                        eq.save(update_fields=["status"])
        except Exception as e:
            logger.warning("Error syncing equipment status: %s", e)
