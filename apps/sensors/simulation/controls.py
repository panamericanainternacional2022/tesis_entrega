import time
import logging
from typing import Optional

from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS, PUMP_FAULT_KEYS, ELEVATOR_FAULT_KEYS, FAULT_NAMES_ES
from apps.sensors.simulation.constants import DEFAULT_SENSOR_DATA
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.globals import simulators
from apps.sensors.simulation.exceptions import (
    SimulatorNotFoundError,
    InvalidDeviceError,
    DeviceNotInBuildingError,
    InvalidFaultTypeError,
)
logger = logging.getLogger(__name__)

_DEVICE_ES = {"pump": "Bomba", "elevator": "Elevador"}


def _clear_device_attrs(sim: BuildingSimulator, device: str | None, attr: str, old_faults: dict) -> None:
    container = getattr(sim, attr, None)
    if not container or not isinstance(container, dict):
        return
    if device == "pump":
        for v in PUMP_VARS:
            container.pop(v, None)
    elif device == "elevator":
        resolved_fault = old_faults.get("elevator")
        if resolved_fault:
            from apps.sensors.simulation.physics.elevator import _get_fault_telemetry_targets
            for v in _get_fault_telemetry_targets(sim, resolved_fault):
                container.pop(v, None)
        else:
            for v in ELEVATOR_VARS:
                container.pop(v, None)
    else:
        container.clear()


def inject_fault(edificio_id: int, device: str, fault_type: str) -> str:
    sim = simulators.get(edificio_id)
    if not sim:
        raise SimulatorNotFoundError(edificio_id)
    if device not in ("pump", "elevator"):
        raise InvalidDeviceError(device)
    if (device == "pump" and not sim.has_pump) or (device == "elevator" and not sim.has_elevator):
        raise DeviceNotInBuildingError(device)
    valid_faults = {
        "pump": PUMP_FAULT_KEYS,
        "elevator": ELEVATOR_FAULT_KEYS,
    }
    if fault_type not in valid_faults[device]:
        raise InvalidFaultTypeError(device, fault_type)

    if device in sim.sim_faults:
        try:
            clear_fault(edificio_id, device)
        except Exception:
            logger.exception("Error al limpiar falla previa en inject_fault")

    sim.sim_faults[device] = fault_type
    sim.fault_injected_at[device] = time.time()

    # Iniciar transición progresiva
    if device == "pump":
        sim.fault_transition_pump = "injecting"
        sim._fault_targets_pump = {}
    elif device == "elevator":
        sim.fault_transition_elev = "injecting"
        sim._fault_targets_elev = {}

    logger.info("Falla inyectada: edificio=%s, device=%s, tipo=%s", edificio_id, device, fault_type)
    nombre_falla = FAULT_NAMES_ES.get(fault_type, fault_type)
    nombre_dispositivo = _DEVICE_ES.get(device, device)
    return f"Falla '{nombre_falla}' inyectada en {nombre_dispositivo}"

def clear_fault(edificio_id: int, device: Optional[str] = None) -> str:
    sim = simulators.get(edificio_id)
    if not sim:
        raise SimulatorNotFoundError(edificio_id)

    old_faults: dict[str, str] = {}
    if device:
        if device in sim.sim_faults:
            old_faults[device] = sim.sim_faults[device]
        sim.sim_faults.pop(device, None)
        sim.fault_injected_at.pop(device, None)
    else:
        old_faults = dict(sim.sim_faults)
        sim.sim_faults.clear()
        sim.fault_injected_at.clear()

    _mark_history_resolved(edificio_id, old_faults)

    keys_to_remove = [k for k in sim.active_alerts if k.startswith("fault_raw:")]
    for k in keys_to_remove:
        sim.active_alerts.pop(k, None)

    if hasattr(sim, "_compound_alert_sent"):
        for old_fault in old_faults.values():
            sim._compound_alert_sent.discard(f"fault_raw:{old_fault}")

    _clear_device_attrs(sim, device, "last_email_sent_time_per_var", old_faults)
    _clear_device_attrs(sim, device, "_alert_consecutive", old_faults)

    for old_dev, old_fault in old_faults.items():
        fault_email_key = f"fault_raw:{old_fault}"
        sim.last_email_sent_time_per_var.pop(fault_email_key, None)
        fault_alert_key = f"fault_raw:{old_fault}"
        sim.active_alerts.pop(fault_alert_key, None)
        if hasattr(sim, "_alert_consecutive"):
            sim._alert_consecutive.pop(fault_alert_key, None)

    from apps.sensors.simulation.fault_recovery import apply_pump_recovery, apply_elevator_recovery, RECOVERY_GRACE_TICKS
    if device in (None, "pump"):
        apply_pump_recovery(sim)
        sim.fault_transition_pump = "recovering"
        sim._fault_transition_ticks_pump = RECOVERY_GRACE_TICKS
    if device in (None, "elevator"):
        apply_elevator_recovery(sim)
        sim.fault_transition_elev = "recovering"
        sim._fault_transition_ticks_elev = RECOVERY_GRACE_TICKS

    if device:
        nombre_dispositivo = _DEVICE_ES.get(device, device)
        msg = f"Falla limpiada para {nombre_dispositivo}"
    else:
        msg = "Todas las fallas limpiadas"
    logger.info(msg)
    return msg


def _mark_history_resolved(edificio_id: int, old_faults: dict[str, str]) -> None:
    if not old_faults:
        return
    try:
        from apps.history.models import History

        for fault_type in old_faults.values():
            History.objects.filter(
                monitoring_equipment__building_id=edificio_id,
                fault_type=fault_type,
                resolved=False,
            ).update(resolved=True)
    except Exception as exc:
        logger.warning("No se pudo marcar alertas como resueltas: %s", exc)


def reset_simulator(edificio_id: int) -> str:
    sim = simulators.get(edificio_id)
    if not sim:
        raise SimulatorNotFoundError(edificio_id)
    sim.sensor_data = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
    sim.pump_on = sim.has_pump
    sim.elevator_on = sim.has_elevator
    sim.active_alerts.clear()
    sim.history.clear()
    sim.pending_alerts.clear()
    sim.sim_faults.clear()
    sim.fault_injected_at.clear()
    if hasattr(sim, "last_email_sent_time_per_var") and isinstance(sim.last_email_sent_time_per_var, dict):
        sim.last_email_sent_time_per_var.clear()
    if hasattr(sim, "_alert_consecutive") and isinstance(sim._alert_consecutive, dict):
        sim._alert_consecutive.clear()

    try:
        from apps.history.models import History
        History.objects.filter(
            monitoring_equipment__building_id=edificio_id,
            resolved=False,
        ).update(resolved=True)
    except Exception as exc:
        logger.warning("No se pudo marcar todas las alertas como resueltas en reinicio: %s", exc)


    sim.protection_on = False
    sim.auto_faults_enabled = False
    sim._auto_fault_ticks = 0.0
    sim._protection_grace_ticks_pump = 0
    sim._protection_grace_ticks_elev = 0

    sim._compound_alert_sent = set()

    sim.fault_transition_pump = "stable"
    sim.fault_transition_elev = "stable"
    sim._fault_transition_ticks_pump = 0
    sim._fault_transition_ticks_elev = 0
    sim._fault_targets_pump = {}
    sim._fault_targets_elev = {}

    sim.sim_paused = True
    sim.sim_started = False
    sim.sim_speed = 1.0
    sim._pump_demand = 15.0
    sim._pump_start_grace_ticks = 5
    sim._elev_state = "IDLE"
    sim._elev_timer = 0
    if sim.has_elevator:
        from apps.sensors.simulation.physics.elevator import _clear_elevator_fault_params
        _clear_elevator_fault_params(sim)
        sim.sensor_data["elev_position"] = 0
        sim._elev_position_meters = 0.0
        sim._elev_target_floor = 0
    else:
        sim._elev_target_floor = 0
        sim._elev_position_meters = 0.0
    sim._elev_direction = 1
    logger.info("Simulador reiniciado: edificio=%s", edificio_id)
    return "Simulador reiniciado al estado normal"


