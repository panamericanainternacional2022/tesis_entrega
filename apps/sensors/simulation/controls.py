import random
import time
import logging
from typing import Optional

from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS, PUMP_FAULT_KEYS, ELEVATOR_FAULT_KEYS, FAULT_NAMES_ES, RISK_INFORMATIVO
from apps.sensors.simulation.constants import (
    DEFAULT_SENSOR_DATA, FLOOR_COUNT, SAFE_RESET_VALUES,
    CLEAR_FAULT_MIN_FLOW, CLEAR_FAULT_MIN_PRESSURE, CLEAR_FAULT_MAX_VIBRATION,
    CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH, CLEAR_FAULT_MAX_LOAD,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.globals import simulators
from apps.sensors.simulation.exceptions import (
    SimulatorNotFoundError,
    InvalidDeviceError,
    DeviceNotInBuildingError,
    InvalidFaultTypeError,
)

logger = logging.getLogger(__name__)

PUMP_RESET_KEYS = [v for v in PUMP_VARS if v in SAFE_RESET_VALUES]
ELEVATOR_RESET_KEYS = [v for v in ELEVATOR_VARS if v in SAFE_RESET_VALUES] + ["temperature"]


def reset_critical_values(targets: set[str], sim: BuildingSimulator) -> None:
    if not targets:
        return
    import time as _time
    from apps.sensors.sensor_config import BOOLEAN_VARS, ENUM_VARS
    PROGRESSIVE_DURATION = 15.0
    expiration = _time.time() + PROGRESSIVE_DURATION
    sd = sim.sensor_data
    if "pump" in targets:
        sim._pump_start_grace_ticks = 5
        for k in PUMP_RESET_KEYS:
            if k in SAFE_RESET_VALUES:
                target_val = SAFE_RESET_VALUES[k]
                current_val = sd.get(k)
                if k in BOOLEAN_VARS or k in ENUM_VARS:
                    sd[k] = target_val
                elif current_val is not None and current_val != target_val:
                    sim.manual_overrides[k] = expiration
                    sim.manual_targets[k] = target_val
                else:
                    sd[k] = target_val
        sim._pump_demand = DEFAULT_SENSOR_DATA["flow_rate"]
    if "elevator" in targets:
        for k in ELEVATOR_RESET_KEYS:
            if k in SAFE_RESET_VALUES:
                target_val = SAFE_RESET_VALUES[k]
                current_val = sd.get(k)
                if k in BOOLEAN_VARS or k in ENUM_VARS:
                    sd[k] = target_val
                elif current_val is not None and current_val != target_val:
                    sim.manual_overrides[k] = expiration
                    sim.manual_targets[k] = target_val
                else:
                    sd[k] = target_val
    sim.door_close_attempts = 0


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
    sim.sim_faults[device] = fault_type
    sim.fault_injected_at[device] = time.time()
    logger.info("Falla inyectada: edificio=%s, device=%s, tipo=%s", edificio_id, device, fault_type)
    _DEVICE_ES = {"pump": "Bomba", "elevator": "Elevador"}
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

    _notify_faults_resolved(edificio_id, old_faults)

    import time as _time
    PROGRESSIVE_DURATION = 15.0

    if hasattr(sim, "manual_overrides") and isinstance(sim.manual_overrides, dict):
        if device == "pump":
            for v in PUMP_VARS:
                sim.manual_overrides.pop(v, None)
        elif device == "elevator":
            for v in ELEVATOR_VARS:
                sim.manual_overrides.pop(v, None)
        else:
            sim.manual_overrides.clear()
    if hasattr(sim, "manual_targets") and isinstance(sim.manual_targets, dict):
        if device == "pump":
            for v in PUMP_VARS:
                sim.manual_targets.pop(v, None)
        elif device == "elevator":
            for v in ELEVATOR_VARS:
                sim.manual_targets.pop(v, None)
        else:
            sim.manual_targets.clear()

    if hasattr(sim, "last_email_sent_time_per_var") and isinstance(sim.last_email_sent_time_per_var, dict):
        if device == "pump":
            for v in PUMP_VARS:
                sim.last_email_sent_time_per_var.pop(v, None)
        elif device == "elevator":
            for v in ELEVATOR_VARS:
                sim.last_email_sent_time_per_var.pop(v, None)
        else:
            sim.last_email_sent_time_per_var.clear()

    _DEVICE_ES = {"pump": "Bomba", "elevator": "Elevador"}
    if device:
        nombre_dispositivo = _DEVICE_ES.get(device, device)
        msg = f"Falla limpiada para {nombre_dispositivo}"
    else:
        msg = "Todas las fallas limpiadas"
    sd = sim.sensor_data
    expiration = _time.time() + PROGRESSIVE_DURATION
    if device in (None, "pump"):
        sim._pump_start_grace_ticks = 5
        if sd.get("flow_rate", 0) < CLEAR_FAULT_MIN_FLOW:
            sim.manual_overrides["flow_rate"] = expiration
            sim.manual_targets["flow_rate"] = CLEAR_FAULT_MIN_FLOW
        if sd.get("pressure", 0) < CLEAR_FAULT_MIN_PRESSURE:
            sim.manual_overrides["pressure"] = expiration
            sim.manual_targets["pressure"] = CLEAR_FAULT_MIN_PRESSURE
        if sd.get("vibration", 0) > CLEAR_FAULT_MAX_VIBRATION:
            sim.manual_overrides["vibration"] = expiration
            sim.manual_targets["vibration"] = CLEAR_FAULT_MAX_VIBRATION
        volt = sd.get("voltage", 220)
        if volt < CLEAR_FAULT_VOLTAGE_LOW or volt > CLEAR_FAULT_VOLTAGE_HIGH:
            sim.manual_overrides["voltage"] = expiration
            sim.manual_targets["voltage"] = _clamp(volt, CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH)
    if device in (None, "elevator"):
        sd["motor_stuck"] = False
        if sd.get("speed", 0) < 0.0:
            sim.manual_overrides["speed"] = expiration
            sim.manual_targets["speed"] = 0.0
        if sd.get("load", 0) > CLEAR_FAULT_MAX_LOAD:
            sim.manual_overrides["load"] = expiration
            sim.manual_targets["load"] = CLEAR_FAULT_MAX_LOAD
        sd["door_status"] = "closed"
        sim.door_close_attempts = 0
        sim._elev_state = "IDLE"
    logger.info(msg)
    return msg


def _notify_faults_resolved(edificio_id: int, old_faults: dict[str, str]) -> None:
    if not old_faults:
        return
    try:
        from apps.events.services.alert_service import persist_notification_in_django
        _DEVICE_ES = {"pump": "Bomba", "elevator": "Elevador"}
        for dev, fault_type in old_faults.items():
            nombre_falla = FAULT_NAMES_ES.get(fault_type, fault_type)
            nombre_dispositivo = _DEVICE_ES.get(dev, dev)
            action = f"Falla '{nombre_falla}' en {nombre_dispositivo} resuelta. Operación normal restaurada."
            persist_notification_in_django(
                f"fault_resolved_{dev}", fault_type, RISK_INFORMATIVO, action, edificio_id=edificio_id,
            )
    except Exception as exc:
        logger.warning("No se pudo enviar notificación de resolución de falla: %s", exc)


def reset_simulator(edificio_id: int) -> str:
    sim = simulators.get(edificio_id)
    if not sim:
        raise SimulatorNotFoundError(edificio_id)
    sim.sensor_data = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
    sim.pump_on = sim.has_pump
    sim.elevator_on = sim.has_elevator
    sim.manual_pump_override = False
    sim.manual_elevator_override = False
    sim.protection_ends.clear()
    sim.active_alerts.clear()
    sim.door_close_attempts = 0
    sim.history.clear()
    sim.pending_notifications.clear()
    sim.sim_faults.clear()
    sim.fault_injected_at.clear()
    if hasattr(sim, "manual_overrides") and isinstance(sim.manual_overrides, dict):
        sim.manual_overrides.clear()
    if hasattr(sim, "manual_targets") and isinstance(sim.manual_targets, dict):
        sim.manual_targets.clear()
    if hasattr(sim, "last_email_sent_time_per_var") and isinstance(sim.last_email_sent_time_per_var, dict):
        sim.last_email_sent_time_per_var.clear()
    sim.sim_paused = False
    sim.sim_speed = 1.0
    sim._pump_demand = 15.0
    sim._pump_start_grace_ticks = 5
    sim._pump_refill_timer = 0
    sim._elev_state = "IDLE"
    sim._elev_timer = 0
    if sim.has_elevator:
        initial_floor = random.randint(0, sim.floors)
        sim.sensor_data["position"] = initial_floor
        sim._elev_position_meters = float(initial_floor * 3.5)
        sim._elev_target_floor = initial_floor
    else:
        sim._elev_target_floor = 0
        sim._elev_position_meters = 0.0
    sim._elev_direction = 1
    sim._elev_at_floor = True
    logger.info("Simulador reiniciado: edificio=%s", edificio_id)
    return "Simulador reiniciado al estado normal"
