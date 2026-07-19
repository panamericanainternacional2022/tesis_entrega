import time
import logging

import eventlet

from apps.sensors.sensor_config import (
    PUMP_VARS, ELEVATOR_VARS,
    RISK_CRITICO, RISK_ALTO, RISK_NORMAL, RISK_COLORS,
    SIM_TICK_INTERVAL, FAULT_AFFECTED_VARIABLES,
    DAILY_PERSIST_INTERVAL, DAILY_RETENTION_DAYS,
    ENUM_VARS, VAR_NAMES, UNITS, FAULT_NAMES_ES)
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
    _check_auto_faults(sim)
    _check_auto_protection(sim)
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
    """Envía UNA sola alerta por cada falla activa, solo cuando todos los sensores
    han completado su rampa progresiva (transition == 'stable')."""
    for device, fault_type in sim.sim_faults.items():
        trans_attr = f'fault_transition_{device}'
        if getattr(sim, trans_attr, 'stable') != 'stable':
            continue

        affected_vars_defs = FAULT_AFFECTED_VARIABLES.get(fault_type, [])

        alert_vars: dict[str, dict] = {}
        worst_risk = RISK_NORMAL
        for var in affected_vars_defs:
            var_risk = risk_cache.get(var, RISK_NORMAL)
            if fault_type in ("pos_sensor_fail", "door_blocked") or var_risk in (RISK_ALTO, RISK_CRITICO):
                alert_vars[var] = {
                    "value": sim.sensor_data.get(var, 0),
                    "risk": var_risk,
                    "display_name": VAR_NAMES.get(var, var),
                    "unit": UNITS.get(var, ""),
                }
                if var_risk == RISK_CRITICO:
                    worst_risk = RISK_CRITICO
                elif worst_risk != RISK_CRITICO and var_risk == RISK_ALTO:
                    worst_risk = RISK_ALTO

        if fault_type == "pos_sensor_fail" and worst_risk == RISK_NORMAL:
            worst_risk = RISK_CRITICO
        elif fault_type == "door_blocked" and worst_risk == RISK_NORMAL:
            worst_risk = RISK_ALTO

        if not alert_vars:
            continue

        fault_key = f"fault_raw:{fault_type}"

        if not hasattr(sim, "_compound_alert_sent"):
            sim._compound_alert_sent = set()
        if fault_key in sim._compound_alert_sent:
            continue

        if not hasattr(sim, "_alert_consecutive"):
            sim._alert_consecutive = {}
        consecutive = sim._alert_consecutive.get(fault_key, 0) + sim.sim_speed
        sim._alert_consecutive[fault_key] = consecutive
        if consecutive < ALERT_DEBOUNCE_TICKS:
            continue

        sim._compound_alert_sent.add(fault_key)

        from apps.history.alerts.engine import send_compound_alert
        send_compound_alert(fault_type, alert_vars, worst_risk, sim)


def _build_history_records(sim: BuildingSimulator, alert_vars: set[str], risk_cache: dict[str, str] = None) -> None:
    thresholds = get_thresholds(sim.edificio_id)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_readings = []
    for var, value in sim.sensor_data.items():
        if var not in alert_vars:
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
        from django.db import transaction
        from django.utils import timezone
        from apps.sensors.models import SensorReading

        with transaction.atomic():
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

    from django.db import close_old_connections

    while True:
        eventlet.sleep(SIM_TICK_INTERVAL)
        close_old_connections()
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
                    "Error en tick de sim %s (%s) - fallo consecutivo #%s",
                    eid, sim.nombre, fails)
                backoff = min(2 ** fails, _MAX_BACKOFF_TICKS)
                _backoff_remaining[eid] = backoff
                logger.warning(
                    "Simulador %s (%s) en backoff por %s ticks - reintentará automáticamente",
                    eid, sim.nombre, backoff)


def _check_auto_faults(sim: BuildingSimulator) -> None:
    if not getattr(sim, 'auto_faults_enabled', False):
        return

    sim._auto_fault_ticks = getattr(sim, '_auto_fault_ticks', 0.0) + sim.sim_speed
    if sim._auto_fault_ticks < 5.0:  # Cada ~5 ticks/segundos de simulación
        return
    sim._auto_fault_ticks = 0.0

    # No inyectar si ya hay fallas o pausas pendientes, o protección reciente
    trans_pump = getattr(sim, 'fault_transition_pump', 'stable')
    trans_elev = getattr(sim, 'fault_transition_elev', 'stable')
    if trans_pump != 'stable' or trans_elev != 'stable':
        import logging; logging.getLogger(__name__).info(f"Auto-fault skipped: trans_pump={trans_pump}, trans_elev={trans_elev}")
        return

    from apps.sensors.simulation.controls import inject_fault
    from apps.sensors.sensor_config import PUMP_FAULT_KEYS, ELEVATOR_FAULT_KEYS
    import random

    candidates = []
    if sim.has_pump and sim.pump_on and not sim.sim_faults.get("pump"):
        candidates.append("pump")
    if sim.has_elevator and sim.elevator_on and not sim.sim_faults.get("elevator"):
        candidates.append("elevator")

    if not candidates:
        import logging; logging.getLogger(__name__).info(f"Auto-fault skipped: no candidates. has_pump={sim.has_pump}, pump_on={sim.pump_on}, sim_faults={sim.sim_faults}, has_elev={sim.has_elevator}, elev_on={sim.elevator_on}")
        return

    device = random.choice(candidates)
    fault = random.choice(PUMP_FAULT_KEYS) if device == "pump" else random.choice(ELEVATOR_FAULT_KEYS)
    import logging; logging.getLogger(__name__).info(f"Auto-fault chosen: {device} -> {fault}")
    try:
        inject_fault(sim.edificio_id, device, fault)
    except Exception as e:
        logger.warning(f"Error auto-injecting fault {fault} on {device}: {e}")

def _check_auto_protection(sim: BuildingSimulator) -> None:
    if not sim.protection_on:
        return
    if not sim.sim_faults:
        return

    for device, fault_type in list(sim.sim_faults.items()):
        trans_attr = f'fault_transition_{device}'
        transition = getattr(sim, trans_attr, 'stable')
        if transition != 'stable':
            continue

        grace_attr = f'_protection_grace_ticks_{device}'
        grace_ticks = getattr(sim, grace_attr, 0) + 1
        setattr(sim, grace_attr, grace_ticks)

        from apps.sensors.simulation.constants import PROTECTION_GRACE_TICKS
        if grace_ticks < PROTECTION_GRACE_TICKS:
            continue

        device_es = "Bomba" if device == "pump" else "Elevador"
        fault_name = FAULT_NAMES_ES.get(fault_type, fault_type)
        fault_type_protection = f"auto_protection_{device}"

        protection_msg = (
            f"La protección automática ha apagado la {device_es} debido "
            f"a la falla detectada: \"{fault_name}\". "
            f"Revise el equipo antes de reencenderlo."
        )

        protection_title = f"Protección automática ({device_es})"

        alert_payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "fault_type": fault_type_protection,
            "original_fault_type": fault_type,
            "fault_name": protection_title,
            "variables": [],
            "risk": "Resuelta",
            "message": protection_msg,
        }
        sim.pending_alerts.append(alert_payload)

        try:
            from django.utils import timezone
            from apps.buildings.models import MonitoringEquipment
            equipo = MonitoringEquipment.objects.filter(
                building_id=sim.edificio_id,
                equipment_type="bomba" if device == "pump" else "elevador",
            ).first()
            if equipo:
                from apps.users.models import Usuario
                from apps.core.auth_decorators import ADMIN_ROLES
                usuario = Usuario.objects.filter(rol__in=ADMIN_ROLES).first() or Usuario.objects.first()
                if usuario:
                    from apps.history.models import History
                    History.objects.create(
                        user=usuario,
                        monitoring_equipment=equipo,
                        date=timezone.now(),
                        message={
                            "risk": "Resuelta",
                            "variable": protection_title,
                            "value": "",
                            "action": protection_msg,
                            "fault_name": protection_title,
                            "variables_detail": [],
                        },
                        fault_type=fault_type_protection,
                        affected_variables=[],
                        resolved=True,
                    )
        except Exception:
            logger.exception("Error guardando registro de protección automática para edificio %s", sim.edificio_id)

        if device == 'pump':
            sim.pump_on = False
        else:
            sim.elevator_on = False

        from apps.sensors.simulation.controls import clear_fault
        clear_fault(sim.edificio_id, device)

        setattr(sim, grace_attr, 0)
