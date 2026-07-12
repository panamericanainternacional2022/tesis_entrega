import random
import time
import logging

from apps.sensors.sensor_config import PUMP_FAULT_KEYS, ELEVATOR_FAULT_KEYS
from apps.sensors.simulation.constants import (
    RANDOM_FAULT_PROB, FAULT_AUTO_CLEAR_SECONDS,
    SIMULTANEOUS_FAIL_PROB, LOG_SIM,
    FLOOR_HEIGHT, MAX_STEPS_PER_SECOND,
)
from apps.sensors.simulation.models import BuildingSimulator

logger = logging.getLogger(__name__)


def update_sensor_data(active_sim: BuildingSimulator) -> None:
    if active_sim.sim_paused:
        return
    _auto_clear_expired_faults(active_sim)
    _apply_manual_override_transitions(active_sim)
    _bridge_manual_overrides_to_faults(active_sim)
    if active_sim.has_pump:
        from apps.sensors.simulation.physics.pump import _update_pump
        _update_pump(active_sim)
    if active_sim.has_elevator:
        from apps.sensors.simulation.physics.elevator import _update_elevator
        _update_elevator(active_sim)
    _inject_random_faults(active_sim)


def _auto_clear_expired_faults(sim: BuildingSimulator) -> None:
    expired = _get_expired_faults(sim)
    for device in expired:
        _clear_expired_fault_device(sim, device)


def _get_expired_faults(sim: BuildingSimulator) -> list:
    now = time.time()
    manual = getattr(sim, "_manual_triggered_faults", set())
    return [
        device
        for device, injected_at in sim.fault_injected_at.items()
        if now - injected_at >= FAULT_AUTO_CLEAR_SECONDS
        and device not in manual
    ]


def _clear_expired_fault_device(sim: BuildingSimulator, device: str) -> None:
    sim.sim_faults.pop(device, None)
    sim.fault_injected_at.pop(device, None)
    if LOG_SIM:
        print(
            f"[SIM] {time.strftime('%H:%M:%S')} "
            f"AUTO-CLEAR: falla de {device} expirada tras {FAULT_AUTO_CLEAR_SECONDS}s"
        )
    from apps.sensors.simulation.fault_recovery import apply_pump_recovery, apply_elevator_recovery
    if device == "pump":
        apply_pump_recovery(sim)
    elif device == "elevator":
        apply_elevator_recovery(sim)


def _inject_random_faults(sim: BuildingSimulator) -> None:
    if sim.sim_faults:
        return
    dt = sim.sim_speed
    pump_can_fault = (
        sim.pump_on
        and random.random() < RANDOM_FAULT_PROB * dt
    )
    elev_can_fault = (
        sim.elevator_on
        and random.random() < RANDOM_FAULT_PROB * dt
    )
    pump_faulted = False
    elev_faulted = False
    if pump_can_fault:
        _inject_random_pump_fault(sim)
        pump_faulted = True
    if elev_can_fault:
        _inject_random_elevator_fault(sim)
        elev_faulted = True
    if pump_faulted and not elev_faulted:
        _maybe_simultaneous_elevator_fault(sim)
    elif elev_faulted and not pump_faulted:
        _maybe_simultaneous_pump_fault(sim)


def _maybe_simultaneous_elevator_fault(sim: BuildingSimulator) -> None:
    if (
        sim.elevator_on
        and random.random() < SIMULTANEOUS_FAIL_PROB
    ):
        _inject_random_elevator_fault(sim)


def _maybe_simultaneous_pump_fault(sim: BuildingSimulator) -> None:
    if (
        sim.pump_on
        and random.random() < SIMULTANEOUS_FAIL_PROB
    ):
        _inject_random_pump_fault(sim)


def _inject_random_pump_fault(sim: BuildingSimulator) -> None:
    fault_type = random.choice(list(PUMP_FAULT_KEYS))
    sim.sim_faults["pump"] = fault_type
    sim.fault_injected_at["pump"] = time.time()
    logger.info("Falla aleatoria de bomba inyectada (vía sim_faults): %s", fault_type)
    if LOG_SIM:
        print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: pump {fault_type}")


def _inject_random_elevator_fault(sim: BuildingSimulator) -> None:
    fault_type = random.choice(list(ELEVATOR_FAULT_KEYS))
    sim.sim_faults["elevator"] = fault_type
    sim.fault_injected_at["elevator"] = time.time()
    logger.info("Falla aleatoria de elevador inyectada (vía sim_faults): %s", fault_type)
    if LOG_SIM:
        print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: elevator {fault_type}")


def _apply_manual_override_transitions(sim: BuildingSimulator) -> None:
    import time as time_lib
    now = time_lib.time()
    dt = sim.sim_speed

    if not hasattr(sim, "manual_overrides") or not isinstance(sim.manual_overrides, dict):
        sim.manual_overrides = {}
    if not hasattr(sim, "manual_targets") or not isinstance(sim.manual_targets, dict):
        sim.manual_targets = {}

    from apps.sensors.sensor_config import SENSOR_RANGES, BOOLEAN_VARS, ENUM_VARS

    for var, expiration in list(sim.manual_overrides.items()):
        if now >= expiration:
            sim.manual_overrides.pop(var, None)
            sim.manual_targets.pop(var, None)
            continue

        if var not in sim.manual_targets:
            continue

        target = sim.manual_targets[var]
        current = sim.sensor_data.get(var)

        if current is None:
            sim.sensor_data[var] = target
            continue

        if var in BOOLEAN_VARS or var in ENUM_VARS:
            sim.sensor_data[var] = target
            continue

        try:
            target_f = float(target)
            current_f = float(current)
        except (ValueError, TypeError):
            sim.sensor_data[var] = target
            continue

        diff = target_f - current_f
        if abs(diff) < 0.01:
            sim.sensor_data[var] = target_f
            continue

        max_step = MAX_STEPS_PER_SECOND.get(var, 999999.0) * dt
        if abs(diff) <= max_step:
            new_val = target_f
        else:
            new_val = current_f + (max_step if diff > 0 else -max_step)

        bounds = SENSOR_RANGES.get(var)
        if bounds:
            new_val = max(bounds[0], min(bounds[1], new_val))

        if var in ("elev_load",):
            new_val = int(round(new_val))
        else:
            new_val = round(new_val, 1)

        sim.sensor_data[var] = new_val

        if var == "elev_position":
            sim._elev_position_meters = float(new_val * FLOOR_HEIGHT)
            sim._elev_target_floor = round(new_val)
            sim._elev_state = "IDLE"
            sim._elev_timer = 0
            sim._elev_current_accel = 0


def _bridge_manual_overrides_to_faults(sim: BuildingSimulator) -> None:
    """Bridge functional redundancy: when manual overrides set sensor values
    that match a known fault condition, activate the corresponding fault
    physics so the simulation reacts consistently regardless of whether the
    fault was injected via simulation controls or manual data injection.

    For example, setting ``motor_stuck = True`` via manual override will
    activate the ``motor_stuck`` fault in the physics engine (torque=0,
    FSM blocked), exactly as if the fault had been triggered from the
    control panel.
    """
    if not hasattr(sim, "_manual_triggered_faults"):
        sim._manual_triggered_faults = set()

    sd = sim.sensor_data
    now = time.time()

    # ── Pump: voltage forced to ~0 → activate power_outage physics ─────
    has_volt_override = (
        "pump_voltage" in sim.manual_overrides
        and now < sim.manual_overrides.get("pump_voltage", 0)
    )
    if has_volt_override and sd.get("pump_voltage", 220) < 10.0:
        if "pump" not in sim.sim_faults:
            sim.sim_faults["pump"] = "power_outage"
            sim.fault_injected_at["pump"] = now + FAULT_AUTO_CLEAR_SECONDS * 2
            sim._manual_triggered_faults.add("pump")
    elif "pump" in sim._manual_triggered_faults and not has_volt_override:
        sim.sim_faults.pop("pump", None)
        sim.fault_injected_at.pop("pump", None)
        sim._manual_triggered_faults.discard("pump")

    # ── Elevator: motor_stuck forced True → activate motor_stuck fault ──
    has_motor_override = (
        "motor_stuck" in sim.manual_overrides
        and now < sim.manual_overrides.get("motor_stuck", 0)
    )
    if has_motor_override and sd.get("motor_stuck") is True:
        if "elevator" not in sim.sim_faults:
            sim.sim_faults["elevator"] = "motor_stuck"
            sim.fault_injected_at["elevator"] = now + FAULT_AUTO_CLEAR_SECONDS * 2
            sim._manual_triggered_faults.add("elevator")
    elif "elevator" in sim._manual_triggered_faults and not has_motor_override:
        sim.sim_faults.pop("elevator", None)
        sim.fault_injected_at.pop("elevator", None)
        sim._manual_triggered_faults.discard("elevator")

    # ── Elevator: load > 900 (Critico) via manual → activate overload physics ──
    has_load_override = (
        "elev_load" in sim.manual_overrides
        and now < sim.manual_overrides.get("elev_load", 0)
    )
    if has_load_override and sd.get("elev_load", 0) > 900:
        if "elevator" not in sim.sim_faults:
            sim.sim_faults["elevator"] = "overload"
            sim.fault_injected_at["elevator"] = now + FAULT_AUTO_CLEAR_SECONDS * 2
            sim._manual_triggered_faults.add("elevator")
    elif "elevator" in sim._manual_triggered_faults and not has_load_override:
        if sim.sim_faults.get("elevator") == "overload":
            sim.sim_faults.pop("elevator", None)
            sim.fault_injected_at.pop("elevator", None)
            sim._manual_triggered_faults.discard("elevator")

