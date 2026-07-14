import time
import logging

from apps.sensors.simulation.constants import (
    FLOOR_HEIGHT, MAX_STEPS_PER_SECOND,
)
from apps.sensors.simulation.models import BuildingSimulator

logger = logging.getLogger(__name__)


def update_sensor_data(active_sim: BuildingSimulator) -> None:
    if active_sim.sim_paused:
        return
    _apply_manual_override_transitions(active_sim)
    _bridge_manual_overrides_to_faults(active_sim)
    if active_sim.has_pump:
        from apps.sensors.simulation.physics.pump import _update_pump
        _update_pump(active_sim)
    if active_sim.has_elevator:
        from apps.sensors.simulation.physics.elevator import _update_elevator
        _update_elevator(active_sim)


def _apply_manual_override_transitions(sim: BuildingSimulator) -> None:
    import time as time_lib
    now = time_lib.time()
    dt = sim.sim_speed

    if not hasattr(sim, "manual_overrides") or not isinstance(sim.manual_overrides, dict):
        sim.manual_overrides = {}
    if not hasattr(sim, "manual_targets") or not isinstance(sim.manual_targets, dict):
        sim.manual_targets = {}

    from apps.sensors.sensor_config import ENUM_VARS

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

        if var in ENUM_VARS:
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

        bounds = sim.sensor_limits.get(var)
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

    For example, setting ``elev_load = 1000`` via manual override will
    activate the ``overload`` fault in the physics engine (torque=0,
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
            sim.fault_injected_at["pump"] = now
            sim._manual_triggered_faults.add("pump")
    elif "pump" in sim._manual_triggered_faults and not has_volt_override:
        sim.sim_faults.pop("pump", None)
        sim.fault_injected_at.pop("pump", None)
        sim._manual_triggered_faults.discard("pump")

    # ── Elevator: load > 900 (Critico) via manual → activate overload physics ──
    has_load_override = (
        "elev_load" in sim.manual_overrides
        and now < sim.manual_overrides.get("elev_load", 0)
    )
    if has_load_override and sd.get("elev_load", 0) > 900:
        if "elevator" not in sim.sim_faults:
            sim.sim_faults["elevator"] = "overload"
            sim.fault_injected_at["elevator"] = now
            sim._manual_triggered_faults.add("elevator")
    elif "elevator" in sim._manual_triggered_faults and not has_load_override:
        if sim.sim_faults.get("elevator") == "overload":
            sim.sim_faults.pop("elevator", None)
            sim.fault_injected_at.pop("elevator", None)
            sim._manual_triggered_faults.discard("elevator")

