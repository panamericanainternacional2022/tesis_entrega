import time
import logging

import eventlet

from apps.sensors.sensor_config import (
    PUMP_VARS, ELEVATOR_VARS,
    RISK_CRITICO, RISK_ALTO, RISK_NORMAL, RISK_COLORS,
    SIM_TICK_INTERVAL, FAULT_AFFECTED_VARIABLES,
    DAILY_PERSIST_INTERVAL, DAILY_RETENTION_DAYS,
    ENUM_VARS)
from apps.sensors.simulation.constants import MAX_HISTORY_SIZE
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.globals import simulators
from apps.sensors.simulation.simulation_engine import update_sensor_data
from apps.core.services.risk_service import classify_risk
from apps.thresholds.services import get_thresholds


logger = logging.getLogger(__name__)

ALERT_DEBOUNCE_TICKS: int = 3
_MAX_BACKOFF_TICKS: int = 30


def _run_sim_tick(sim: BuildingSimulator) -> None:
    if sim.sim_paused:
        return
    update_sensor_data(active_sim=sim)
    alert_vars = _get_alert_vars(sim)
    risk_cache = _process_sensor_alerts(sim, alert_vars)
    _build_history_records(sim, alert_vars, risk_cache)


def _get_alert_vars(sim: BuildingSimulator) -> set[str]:
    alert_vars = set()
    if "bomba" in sim.equipment_types:
        alert_vars.update(PUMP_VARS)
    if "elevador" in sim.equipment_types:
        alert_vars.update(ELEVATOR_VARS)
    return alert_vars


def _process_sensor_alerts(sim: BuildingSimulator, alert_vars: set[str]) -> dict:
    thresholds = get_thresholds(sim.edificio_id)
    risk_cache: dict[str, str] = {}

    for var, value in sim.sensor_data.items():
        if var not in alert_vars:
            continue
        risk, _ = classify_risk(var, value, thresholds)
        risk_cache[var] = risk

    if sim.sim_faults:
        _send_compound_alerts_for_faults(sim, risk_cache)

    return risk_cache


def _send_compound_alerts_for_faults(sim: BuildingSimulator, risk_cache: dict[str, str]) -> None:
    """Envía UNA sola alerta por cada falla activa con todas las variables afectadas."""
    for device, fault_type in sim.sim_faults.items():
        affected_vars_defs = FAULT_AFFECTED_VARIABLES.get(fault_type, [])

        alert_vars: dict[str, dict] = {}
        worst_risk = RISK_NORMAL
        for var in affected_vars_defs:
            if var in risk_cache and risk_cache[var] in (RISK_ALTO, RISK_CRITICO):
                alert_vars[var] = {
                    "value": sim.sensor_data.get(var, 0),
                    "risk": risk_cache[var],
                }
                if risk_cache[var] == RISK_CRITICO:
                    worst_risk = RISK_CRITICO
                elif worst_risk != RISK_CRITICO and risk_cache[var] == RISK_ALTO:
                    worst_risk = RISK_ALTO

        if not alert_vars:
            continue

        fault_key = f"fault_raw:{fault_type}"
        if sim.active_alerts.get(fault_key) == worst_risk:
            continue

        if not hasattr(sim, "_alert_consecutive"):
            sim._alert_consecutive = {}
        consecutive = sim._alert_consecutive.get(fault_key, 0) + sim.sim_speed
        sim._alert_consecutive[fault_key] = consecutive
        if consecutive < ALERT_DEBOUNCE_TICKS:
            continue

        sim.active_alerts[fault_key] = worst_risk

        from apps.history.alerts.engine import send_compound_alert
        send_compound_alert(fault_type, alert_vars, worst_risk, sim)


def _build_history_records(sim: BuildingSimulator, alert_vars: set[str], risk_cache: dict[str, str] = None) -> None:
    thresholds = get_thresholds(sim.edificio_id)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_readings = []
    for var, value in sim.sensor_data.items():
        if var not in alert_vars:
            continue
        # Skip pump readings during start-up grace period (no pump fault active)
        if var in PUMP_VARS and getattr(sim, "_pump_start_grace_ticks", 0) > 0 and not sim.sim_faults.get("pump"):
            continue
        if var in ENUM_VARS:
            continue
        if risk_cache and var in risk_cache:
            risk = risk_cache[var]
        else:
            risk, _ = classify_risk(var, value, thresholds)
        color = RISK_COLORS.get(risk, {}).get("email", {}).get("text", "#475569")
        sensor_type = "Bomba" if var in PUMP_VARS else "Elevador"
        new_readings.append({
            "timestamp": timestamp,
            "type": sensor_type,
            "variable": var,
            "value": value,
            "risk": risk,
            "color": color,
        })
    sim.history.extend(new_readings)
    if len(sim.history) > MAX_HISTORY_SIZE:
        sim.history = sim.history[-MAX_HISTORY_SIZE:]

    sim._persist_tick = getattr(sim, "_persist_tick", 0) + sim.sim_speed
    if sim._persist_tick >= DAILY_PERSIST_INTERVAL:
        sim._persist_tick = 0
        _persist_readings(sim, new_readings)


def _persist_readings(sim: BuildingSimulator, readings: list[dict]) -> None:
    try:
        from django.utils import timezone
        from apps.sensors.models import SensorReading

        now = timezone.now()
        cutoff = now - timezone.timedelta(days=DAILY_RETENTION_DAYS)
        SensorReading.objects.filter(
            building_id=sim.edificio_id, timestamp__lt=cutoff
        ).delete()

        to_create = [
            SensorReading(
                building_id=sim.edificio_id,
                variable=r["variable"],
                value=r["value"],
                risk=r["risk"],
            )
            for r in readings
        ]
        SensorReading.objects.bulk_create(to_create, batch_size=200)
    except Exception:
        logger.exception("Error persistiendo lecturas para edificio %s", sim.edificio_id)


def generate_data_and_emit() -> None:
    _consecutive_failures: dict[int, int] = {}
    _backoff_remaining: dict[int, int] = {}

    while True:
        eventlet.sleep(SIM_TICK_INTERVAL)
        for sim in list(simulators.values()):
            eid = sim.edificio_id

            if _backoff_remaining.get(eid, 0) > 0:
                _backoff_remaining[eid] -= 1
                continue

            try:
                _run_sim_tick(sim)
                _consecutive_failures.pop(eid, None)
                _backoff_remaining.pop(eid, None)
            except Exception:
                fails = _consecutive_failures.get(eid, 0) + 1
                _consecutive_failures[eid] = fails
                logger.exception(
                    "Error en tick de sim %s (%s) — fallo consecutivo #%s",
                    eid, sim.nombre, fails)
                backoff = min(2 ** fails, _MAX_BACKOFF_TICKS)
                _backoff_remaining[eid] = backoff
                logger.warning(
                    "Simulador %s (%s) en backoff por %s ticks — reintentará automáticamente",
                    eid, sim.nombre, backoff)
