import random
import time

from apps.sensors.sensor_config import SENSOR_RANGES, ELEVATOR_VARS, BOOLEAN_VARS, ENUM_VARS, RISK_CRITICO
from apps.sensors.simulation.constants import (
    T_AMBIENT, FLOOR_HEIGHT,
    CRUISING_SPEED, ACCELERATION, PASSENGER_WAIT_TICKS,
    JERK, G, CABIN_EMPTY_MASS, COUNTERWEIGHT_MASS, MOTOR_EFFICIENCY,
    DOOR_OPEN_TIME, DOOR_CLOSE_TIME, RATED_LOAD,
    OVERLOAD_EXTRA_KG,
    POWER_OUTAGE_BRAKE_TIME, POWER_OUTAGE_BATTERY_WAIT,
    BATTERY_RESCUE_SPEED,
    OVERSPEED_GOVERNOR_TRIGGER, OVERSPEED_ACCEL_RATE,
    MAX_STEPS_PER_SECOND,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.utils import clamp, is_locked

_LOAD_LOW, _LOAD_HIGH = SENSOR_RANGES["load"]
_ENERGY_LOW, _ENERGY_HIGH = SENSOR_RANGES["energy"]
_TEMP_LOW, _TEMP_HIGH = SENSOR_RANGES["temperature"]
_SPEED_LOW, _SPEED_HIGH = SENSOR_RANGES["speed"]


def _effective_load(sim: BuildingSimulator, base_load: float) -> float:
    """Return the effective load including any overload fault extra mass."""
    if hasattr(sim, "_elev_overload_extra_kg"):
        return base_load + sim._elev_overload_extra_kg
    return base_load


def _clear_elevator_fault_params(sim: BuildingSimulator) -> None:
    """Reset all physical fault parameters to their default values."""
    sim._elev_motor_torque_factor = 1.0
    sim._elev_door_obstructed = False
    sim._elev_speed_governor_failed = False
    sim._elev_overload_extra_kg = 0.0
    sim._elev_pos_sensor_stuck = False
    sim._elev_power_available = True
    sim._elev_brake_failed = False
    sim._elev_power_outage_timer = 0.0
    sim._elev_power_outage_complete = False
    sim._elev_pos_sensor_mismatch_timer = 0.0


# ---------------------------------------------------------------------------
#  FAULT PARAM SETTERS
#  Each fault handler mutates physical parameters on the simulator.
#  The FSM + physics engine (below) consume these parameters to produce
#  realistic emergent behavior. No sensor values are forced here.
# ---------------------------------------------------------------------------

def _set_motor_stuck_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    """Motor produces zero torque. Contrapeso + carga determinan movimiento."""
    sim._elev_motor_torque_factor = 0.0


def _set_door_blocked_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    """Objeto físico impide cerrar la puerta."""
    sim._elev_door_obstructed = True


def _set_overspeed_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    """Falla del gobernador de velocidad + freno. Velocidad sin regulación."""
    sim._elev_speed_governor_failed = True
    sim._elev_brake_failed = True


def _set_overload_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    """Masa virtual extra que excede capacidad nominal."""
    sim._elev_overload_extra_kg = OVERLOAD_EXTRA_KG


def _set_pos_sensor_fail_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    """Sensor de posición congelado. La física interna sigue pero la lectura no."""
    sim._elev_pos_sensor_stuck = True
    if not hasattr(sim, "_elev_pos_stuck_value"):
        sim._elev_pos_stuck_value = round(sim._elev_position_meters / FLOOR_HEIGHT, 1)


def _set_power_outage_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    """Corte total de energía comercial. Sin torque en motor."""
    sim._elev_power_available = False
    sim._elev_motor_torque_factor = 0.0
    sd["energy"] = 0.0


# ---------------------------------------------------------------------------
#  MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def _snapshot_protected_values(sim: BuildingSimulator, sd: dict) -> dict:
    """Save sensor values that must survive FSM execution.

    Includes:
      - Manual override values (user-set sensor targets)
      - Active fault telemetry values (progressive step from previous tick)
    Manual overrides are excluded when a fault already controls that variable
    (faults take priority).
    """
    protected: dict = {}
    now = time.time()

    fault_vars: set = set()
    fault = sim.sim_faults.get("elevator") if hasattr(sim, "sim_faults") else None
    if fault:
        fault_vars = set(_get_fault_telemetry_targets(sim, fault).keys())

    if hasattr(sim, "manual_overrides") and isinstance(sim.manual_overrides, dict):
        for var, exp in sim.manual_overrides.items():
            if now < exp and var not in fault_vars:
                protected[var] = sd.get(var)

    if fault:
        for var in _get_fault_telemetry_targets(sim, fault):
            protected[var] = sd.get(var)

    return protected


def _restore_protected(sd: dict, protected: dict) -> None:
    """Restore sensor values that FSM handlers may have overwritten."""
    for var, val in protected.items():
        if val is not None:
            sd[var] = val


def _update_elevator(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed
    if not sim.elevator_on:
        _set_elevator_idle(sim, sd, dt)
        _clear_elevator_fault_params(sim)
        return

    protected = _snapshot_protected_values(sim, sd)

    if "elevator" in sim.sim_faults:
        _apply_elevator_fault_params(sim, sd, dt)
    else:
        _clear_elevator_fault_params(sim)

    # FSM + post-FSM SIEMPRE se ejecutan (usan los parámetros físicos)
    _run_elevator_fsm(sim, sd, dt)

    # Restore los valores que el FSM haya pisado (speed, door_status, load)
    _restore_protected(sd, protected)

    # Fallas de simulación: telemetría progresiva gana sobre todo
    if "elevator" in sim.sim_faults:
        _force_elevator_fault_telemetry(sim, sd)


def _get_fault_telemetry_targets(sim: BuildingSimulator, fault: str) -> dict:
    targets = {
        "motor_stuck": {
            "motor_stuck": True,
            "speed": 0.0,
            "energy": _ENERGY_HIGH,
            "door_status": "closed",
            "elevator_state": "STUCK",
        },
        "door_blocked": {
            "door_status": "closing",
            "speed": 0.0,
            "energy": _ENERGY_HIGH * 0.1,
            "door_close_attempts": 3,
            "elevator_state": "DOORS_OPEN",
        },
        "overspeed": {
            "speed": _SPEED_HIGH * 0.75,
            "energy": _ENERGY_LOW * 0.1,
            "door_status": "closed",
            "elevator_state": "MOVING",
        },
        "overload": {
            "load": _LOAD_HIGH * 0.85,
            "door_status": "open",
            "speed": 0.0,
            "energy": _ENERGY_HIGH * 0.02,
            "elevator_state": "DOORS_OPEN",
        },
        "pos_sensor_fail": {
            "position": getattr(sim, "_elev_pos_stuck_value", FLOOR_HEIGHT * 1.25),
            "speed": CRUISING_SPEED,
            "door_status": "closed",
            "elevator_state": "MOVING",
        },
    }
    if fault == "commercial_power_outage":
        timer = getattr(sim, "_elev_power_outage_timer", 0.0)
        complete = getattr(sim, "_elev_power_outage_complete", False)
        from apps.sensors.simulation.constants import (
            POWER_OUTAGE_BRAKE_TIME, POWER_OUTAGE_BATTERY_WAIT,
            BATTERY_RESCUE_SPEED
        )
        if complete:
            return {
                "energy": 0.0,
                "speed": 0.0,
                "door_status": "open",
                "elevator_state": "DOORS_OPEN",
            }
        elif timer < POWER_OUTAGE_BRAKE_TIME:
            return {
                "energy": 0.0,
                "speed": 0.0,
                "door_status": "closed",
            }
        elif timer < POWER_OUTAGE_BATTERY_WAIT:
            return {
                "energy": 0.0,
                "speed": 0.0,
                "door_status": "closed",
                "elevator_state": "IDLE",
            }
        else:
            return {
                "energy": 0.0,
                "speed": BATTERY_RESCUE_SPEED,
                "door_status": "closed",
            }
    return targets.get(fault, {})


def _force_elevator_fault_telemetry(sim: BuildingSimulator, sd: dict) -> None:
    fault = sim.sim_faults.get("elevator")
    if not fault:
        return

    targets = _get_fault_telemetry_targets(sim, fault)
    dt = max(sim.sim_speed, 0.01)

    for var, target in targets.items():
        if var in BOOLEAN_VARS or var in ENUM_VARS:
            sd[var] = target
            if var == "door_close_attempts":
                sim.door_close_attempts = target
            continue

        if var == "door_close_attempts":
            sd[var] = target
            sim.door_close_attempts = target
            continue

        current = sd.get(var)
        if current is None:
            sd[var] = target
            continue

        try:
            diff = float(target) - float(current)
        except (ValueError, TypeError):
            sd[var] = target
            continue

        if abs(diff) < 0.01:
            sd[var] = target
            continue

        max_step = MAX_STEPS_PER_SECOND.get(var, 999999.0) * dt
        if fault == "commercial_power_outage" and var == "speed":
            from apps.sensors.simulation.constants import POWER_OUTAGE_BRAKE_TIME
            timer = getattr(sim, "_elev_power_outage_timer", 0.0)
            complete = getattr(sim, "_elev_power_outage_complete", False)
            if not complete and timer < POWER_OUTAGE_BRAKE_TIME:
                max_step = 2.5 * dt

        if abs(diff) <= max_step:
            new_val = target
        else:
            new_val = float(current) + (max_step if diff > 0 else -max_step)

        bounds = SENSOR_RANGES.get(var)
        if bounds:
            new_val = max(bounds[0], min(bounds[1], new_val))

        if var in ("load", "trip_count"):
            new_val = int(round(new_val))
        else:
            new_val = round(new_val, 1)

        sd[var] = new_val


def _set_elevator_idle(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    if not is_locked(sim, "speed"):
        sd["speed"] = 0.0
    if not is_locked(sim, "load"):
        sd["load"] = int(max(0, sd["load"] - 50 * dt))
    if not is_locked(sim, "energy"):
        sd["energy"] = 0.0
    if not is_locked(sim, "motor_stuck"):
        sd["motor_stuck"] = False
    if not is_locked(sim, "door_close_attempts"):
        sim.door_close_attempts = 0
        sd["door_close_attempts"] = 0
    sim._elev_state = "IDLE"
    sim._elev_stuck_timer = 0.0
    sim._elev_current_accel = 0.0


def _apply_elevator_fault_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    """Apply physical parameters for the active elevator fault.

    First clears ALL old fault parameters, then applies only the
    current fault's parameters.  This prevents cross-contamination
    when switching from one fault type to another.

    Power-outage state machine variables (timer, complete) are
    preserved across the clear so multi-phase state continues
    correctly across ticks.
    """
    _saved_power_outage_timer = sim._elev_power_outage_timer
    _saved_power_outage_complete = sim._elev_power_outage_complete
    _clear_elevator_fault_params(sim)
    sim._elev_power_outage_timer = _saved_power_outage_timer
    sim._elev_power_outage_complete = _saved_power_outage_complete
    fault_type = sim.sim_faults.get("elevator")
    _ELEV_FAULT_PARAM_SETTERS = {
        "motor_stuck":             _set_motor_stuck_params,
        "door_blocked":            _set_door_blocked_params,
        "overspeed":               _set_overspeed_params,
        "overload":                _set_overload_params,
        "pos_sensor_fail":         _set_pos_sensor_fail_params,
        "commercial_power_outage": _set_power_outage_params,
    }
    handler = _ELEV_FAULT_PARAM_SETTERS.get(fault_type)
    if handler:
        handler(sim, sd, dt)


# ---------------------------------------------------------------------------
#  POWER OUTAGE HANDLER  (intercepts FSM when power is unavailable)
# ---------------------------------------------------------------------------

def _handle_power_outage_fsm(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float,
) -> None:
    """Power-outage-specific FSM that replaces the normal state machine.

    Phases:
      0–BRAKE_TIME    : Emergency brake engages (rapid deceleration)
      BRAKE–WAIT      : Standby, waiting for battery power-up
      WAIT+           : Battery rescue at low speed toward nearest floor

    Once battery rescue completes, the elevator stays at the rescue floor
    with doors open (no infinite loop).
    """
    if sim._elev_power_outage_complete:
        sd["speed"] = 0.0
        sd["door_status"] = "open"
        sd["energy"] = 0.0
        return

    sim._elev_power_outage_timer += dt
    timer = sim._elev_power_outage_timer

    if timer < POWER_OUTAGE_BRAKE_TIME:
        # Emergency brake: rapid deceleration independent of motor
        spd = max(0.0, spd - 2.5 * dt)
        sd["speed"] = round(spd, 1)
        sd["door_status"] = "closed"
        sim._elev_position_meters = clamp(
            sim._elev_position_meters + spd * sim._elev_direction * dt,
            0, sim.floors * FLOOR_HEIGHT,
        )
        sd["position"] = round(sim._elev_position_meters / FLOOR_HEIGHT, 1)
        if spd <= 0.01:
            sim._elev_state = "IDLE"
        return

    if timer < POWER_OUTAGE_BATTERY_WAIT:
        # Waiting for battery system to power up
        spd = 0.0
        sd["speed"] = 0.0
        sd["door_status"] = "closed"
        sim._elev_state = "IDLE"
        return

    # Battery rescue mode: creep at low speed toward nearest floor
    spd = BATTERY_RESCUE_SPEED
    floor_num_float = sim._elev_position_meters / FLOOR_HEIGHT
    nearest_floor = round(floor_num_float)
    target_m = nearest_floor * FLOOR_HEIGHT
    diff = target_m - sim._elev_position_meters
    direction = 1 if diff > 0 else -1

    sim._elev_position_meters += spd * direction * dt
    sim._elev_position_meters = clamp(
        sim._elev_position_meters, 0, sim.floors * FLOOR_HEIGHT,
    )
    sd["position"] = round(sim._elev_position_meters / FLOOR_HEIGHT, 1)
    sd["speed"] = round(spd, 1)
    sd["door_status"] = "closed"

    # Arrived at the rescue floor → stay here with doors open
    if abs(sim._elev_position_meters - target_m) < 0.3:
        sd["speed"] = 0.0
        sd["door_status"] = "open"
        sim._elev_state = "DOORS_OPEN"
        sd["energy"] = 0.0
        sim._elev_power_outage_complete = True


# ---------------------------------------------------------------------------
#  ELEVATOR FSM
# ---------------------------------------------------------------------------

def _run_elevator_fsm(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    # Emergency stop / safety interlock check:
    is_moving_state = sim._elev_state in ("ACCELERATING", "MOVING", "DECELERATING")
    if is_moving_state and sd.get("door_status") != "closed" and sd.get("door_status") != "closing":
        sd["speed"] = 0.0
        if sim._elev_state != "DOOR_OPENING":
            sim._elev_state = "DOOR_OPENING"
            sim._elev_timer = 0.0

    # Power outage has its own FSM that replaces the normal one
    if not sim._elev_power_available:
        prev_pos = sim._elev_position_meters
        spd = sd.get("speed", 0.0)
        pos = sim._elev_position_meters
        load = sd.get("load", 0)
        _state_before_outage = sim._elev_state  # save BEFORE outage FSM modifies it
        _handle_power_outage_fsm(sim, sd, dt, spd, pos, load)
        _run_elevator_post_fsm(
            sim, sd, dt, prev_pos,
            sd.get("speed", 0.0), sd.get("load", 0),
            sd.get("door_status", "closed"), _state_before_outage,
        )
        return

    sim._elev_timer += dt
    prev_pos = sim._elev_position_meters
    pos = sim._elev_position_meters
    spd = sd["speed"]
    load = sd["load"]
    door = sd["door_status"]
    state = sim._elev_state
    target = sim._elev_target_floor * FLOOR_HEIGHT
    direction = sim._elev_direction
    _ELEV_STATE_HANDLERS = {
        "IDLE": _handle_elev_idle,
        "DOOR_OPENING": _handle_elev_door_opening,
        "DOORS_OPEN": _handle_elev_doors_open,
        "DOOR_CLOSING": _handle_elev_door_closing,
        "ACCELERATING": _handle_elev_accelerating,
        "MOVING": _handle_elev_moving,
        "DECELERATING": _handle_elev_decelerating,
    }
    handler = _ELEV_STATE_HANDLERS.get(state)
    if handler:
        handler(sim, sd, dt, spd, pos, load, door, target, direction)
    spd = sd["speed"]
    door = sd["door_status"]
    load = sd["load"]
    _run_elevator_post_fsm(sim, sd, dt, prev_pos, spd, load, door, state)


def _handle_elev_idle(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "closed"
    if "elevator" in sim.sim_faults:
        sim._elev_timer = 0
    elif sim._elev_timer >= random.uniform(2, 5):
        sim._elev_timer = 0
        sim._elev_target_floor = random.randint(0, sim.floors)
        floor_num = round(pos / FLOOR_HEIGHT)
        while sim._elev_target_floor == floor_num:
            sim._elev_target_floor = random.randint(0, sim.floors)
        sim._elev_direction = 1 if sim._elev_target_floor > floor_num else -1
        sim._elev_state = "DOOR_OPENING"
    sd["speed"] = spd
    sd["door_status"] = door


def _handle_elev_door_opening(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "opening"
    if sim._elev_timer >= DOOR_OPEN_TIME / max(sim.sim_speed, 0.1):
        sim._elev_timer = 0
        sim._elev_state = "DOORS_OPEN"
    sd["speed"] = spd
    sd["door_status"] = door
    sd["load"] = round(load)


def _handle_elev_doors_open(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "open"
    if sim._elev_timer >= PASSENGER_WAIT_TICKS / max(sim.sim_speed, 0.1):
        sim._elev_timer = 0
        if not is_locked(sim, "load"):
            normal_max = int(RATED_LOAD * 1.1)
            load = clamp(load + random.randint(-150, 150), 0, normal_max)
        sim._elev_state = "DOOR_CLOSING"
    sd["speed"] = spd
    sd["door_status"] = door
    sd["load"] = round(load)


def _handle_elev_door_closing(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "closing"

    # Overload detection (physical door motor can't overcome cabin sag)
    total_load = _effective_load(sim, load)
    if total_load > RATED_LOAD * 1.8:
        sim._elev_state = "DOOR_OPENING"
        sim._elev_timer = 0
        sd["door_status"] = "open"
        sd["speed"] = 0.0
        sim.door_close_attempts += 1
        sd["door_close_attempts"] = sim.door_close_attempts
        return

    from apps.sensors.simulation.constants import MAX_DOOR_CLOSE_ATTEMPTS
    if sim._elev_timer >= DOOR_CLOSE_TIME / max(sim.sim_speed, 0.1):
        door_obstructed = sim._elev_door_obstructed
        overload_fault_active = (
            sim._elev_overload_extra_kg > 0
            and total_load > RATED_LOAD * 1.0
        )
        is_locked_open = is_locked(sim, "door_status") and sd.get("door_status") != "closed"
        random_fail = random.random() < 0.02 * dt

        if door_obstructed or overload_fault_active or is_locked_open or random_fail:
            sim.door_close_attempts += 1
            sd["door_close_attempts"] = sim.door_close_attempts
            if sim.door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
                sim._elev_state = "DOORS_OPEN"
                sim._elev_timer = 0
                sd["door_status"] = "open"
                sd["speed"] = 0.0
                return
            else:
                sim._elev_state = "DOOR_OPENING"
                sim._elev_timer = 0
                sd["door_status"] = "opening"
                sd["speed"] = 0.0
                return

        floor_num = round(pos / FLOOR_HEIGHT)
        if floor_num == sim._elev_target_floor:
            sim._elev_timer = 0
            sim._elev_state = "IDLE"
            sd["door_status"] = "closed"
            sd["speed"] = 0.0
            return
        else:
            sim._elev_timer = 0
            sim._elev_state = "ACCELERATING"
            sim._elev_at_floor = False
            sim._elev_current_accel = 0
            sd["door_status"] = "closed"
            sd["speed"] = 0.0
            return


def _handle_elev_accelerating(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    prev_spd = spd
    # If motor torque is zero, the elevator cannot accelerate
    if sim._elev_motor_torque_factor <= 0:
        sim._elev_state = "MOVING"
        sim._elev_current_accel = 0.0
        sd["speed"] = 0.0
        sd["door_status"] = "closed"
        sim._elev_position_meters = pos
        return

    effective_jerk = JERK * sim._elev_motor_torque_factor
    max_accel = ACCELERATION * sim._elev_motor_torque_factor
    sim._elev_current_accel = min(
        sim._elev_current_accel + effective_jerk * dt,
        max(0, max_accel),
    )
    # No acceleration limit from governor during this phase
    speed_cap = CRUISING_SPEED if not sim._elev_speed_governor_failed else CRUISING_SPEED * 3
    spd = clamp(spd + sim._elev_current_accel * dt, 0, speed_cap)
    door = "closed"
    pos += (prev_spd + spd) / 2 * direction * dt
    if spd >= CRUISING_SPEED * 0.9 and not sim._elev_speed_governor_failed:
        sim._elev_state = "MOVING"
        sim._elev_current_accel = 0.0
    elif spd >= speed_cap * 0.9:
        sim._elev_state = "MOVING"
        sim._elev_current_accel = 0.0
    sd["speed"] = spd
    sd["door_status"] = door
    sim._elev_position_meters = pos


def _handle_elev_moving(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    door = "closed"

    if sim._elev_speed_governor_failed and sim._elev_motor_torque_factor > 0:
        # No speed regulation: motor keeps accelerating
        spd = spd + OVERSPEED_ACCEL_RATE * dt
        # Safety brake as last resort (unless brake also failed)
        if spd > CRUISING_SPEED * OVERSPEED_GOVERNOR_TRIGGER and not sim._elev_brake_failed:
            spd = 0.0
            sim._elev_state = "IDLE"
            sim._elev_timer = 0
            sd["speed"] = spd
            sd["door_status"] = door
            sim._elev_position_meters = pos
            sd["position"] = round(pos / FLOOR_HEIGHT, 1)
            return
    elif sim._elev_motor_torque_factor <= 0:
        # Motor stuck or no power: decelerate from friction + gravity
        spd = max(0.0, spd - 1.5 * dt)
        if spd <= 0.01:
            spd = 0.0
            sim._elev_state = "IDLE"
            sim._elev_timer = 0
    else:
        spd = CRUISING_SPEED + random.uniform(-0.1, 0.1) * dt

    pos += spd * direction * dt
    stopping_distance = (spd ** 2) / (2 * ACCELERATION) + 0.5
    if direction > 0 and pos >= target - stopping_distance:
        sim._elev_state = "DECELERATING"
        sim._elev_timer = 0
        sim._elev_current_accel = 0
    elif direction < 0 and pos <= target + stopping_distance:
        sim._elev_state = "DECELERATING"
        sim._elev_timer = 0
        sim._elev_current_accel = 0
    sd["speed"] = spd
    sd["door_status"] = door
    sim._elev_position_meters = pos


def _handle_elev_decelerating(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    prev_spd = spd
    effective_jerk = JERK * sim._elev_motor_torque_factor
    max_dec = ACCELERATION * (0.5 if sim._elev_motor_torque_factor <= 0 else 1.0)
    sim._elev_current_accel = max(
        sim._elev_current_accel - effective_jerk * dt,
        -max_dec,
    )
    if sim._elev_speed_governor_failed:
        spd = spd + OVERSPEED_ACCEL_RATE * dt
    else:
        spd = clamp(spd + sim._elev_current_accel * dt, 0, CRUISING_SPEED)
    door = "closed"
    pos += (prev_spd + spd) / 2 * direction * dt
    if spd <= 0.05:
        spd = 0.0
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
        sim._elev_timer = 0
        sim._elev_state = "DOOR_OPENING"
        sim._elev_at_floor = True
        sim._elev_current_accel = 0
    elif sim._elev_speed_governor_failed and (pos >= sim.floors * FLOOR_HEIGHT or pos <= 0):
        spd = 0.0
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
        sim._elev_timer = 0
        sim._elev_state = "IDLE"
        sim._elev_at_floor = True
        sim._elev_current_accel = 0
    sd["speed"] = spd
    sd["door_status"] = door
    sim._elev_position_meters = pos


# ---------------------------------------------------------------------------
#  POST-FSM
# ---------------------------------------------------------------------------

def _run_elevator_post_fsm(
    sim: BuildingSimulator, sd: dict, dt: float,
    prev_pos: float, spd: float,
    load: float, door: str, old_state: str,
) -> None:
    pos = clamp(sim._elev_position_meters, 0, sim.floors * FLOOR_HEIGHT)
    sim._elev_position_meters = pos
    current_state = sim._elev_state
    if current_state in ("IDLE", "DOOR_OPENING", "DOORS_OPEN", "DOOR_CLOSING"):
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
        sim._elev_position_meters = pos
    if not is_locked(sim, "door_close_attempts"):
        if spd != 0:
            sim.door_close_attempts = 0
            sd["door_close_attempts"] = 0
        if current_state == "DOOR_CLOSING" and sim._elev_timer >= DOOR_CLOSE_TIME / max(sim.sim_speed, 0.1):
            if random.random() < 0.15 * dt:
                sim.door_close_attempts += 1
                sd["door_close_attempts"] = sim.door_close_attempts
                if door == "closed":
                    sim._elev_state = "DOOR_OPENING"
                    sim._elev_timer = 0

    if "elevator" not in sim.sim_faults:
        moving_states = {"ACCELERATING", "MOVING", "DECELERATING"}
        if old_state in moving_states and current_state not in moving_states:
            has_critico = any(risk == RISK_CRITICO for risk in sim.active_alerts.values())
            if not has_critico and not is_locked(sim, "trip_count") and abs(pos - prev_pos) > 0.5:
                sd["trip_count"] += 1

    # Include overload extra kg in energy and stuck computations
    effective_load = _effective_load(sim, load)
    energy = _compute_elevator_energy(effective_load, spd, current_state, sim)
    
    # Check position sensor mismatch
    if sim._elev_pos_sensor_stuck:
        if not hasattr(sim, "_elev_pos_sensor_mismatch_timer"):
            sim._elev_pos_sensor_mismatch_timer = 0.0
        if abs(spd) > 0.05:
            sim._elev_pos_sensor_mismatch_timer += dt
            if sim._elev_pos_sensor_mismatch_timer >= 4.0:
                sim._elev_state = "IDLE"
                sd["speed"] = 0.0
                spd = 0.0
                sim._elev_motor_torque_factor = 0.0
                sim._elev_brake_failed = False
    else:
        sim._elev_pos_sensor_mismatch_timer = 0.0

    stuck = _check_motor_stuck(sim, current_state, spd, effective_load, sd.get("temperature", 50.0), dt)
    if stuck:
        energy = 15.0

    # Power outage forces energy to 0
    if not sim._elev_power_available:
        energy = 0.0

    if not is_locked(sim, "position") and not sim._elev_pos_sensor_stuck:
        sd["position"] = round(sim._elev_position_meters / FLOOR_HEIGHT, 1)
    elif sim._elev_pos_sensor_stuck:
        # Position sensor frozen: keep the old reading
        pass

    if not is_locked(sim, "speed"):
        sd["speed"] = round(spd, 1)
    if not is_locked(sim, "load"):
        sd["load"] = round(load)
    if not is_locked(sim, "door_status"):
        sd["door_status"] = door
    if not is_locked(sim, "energy"):
        sd["energy"] = round(clamp(energy, _ENERGY_LOW, _ENERGY_HIGH), 1)
    if not is_locked(sim, "motor_stuck"):
        sd["motor_stuck"] = stuck

    # Synchronize elevator_state
    sd["elevator_state"] = current_state

    sim._elev_prev_position = prev_pos


def _compute_elevator_energy(
    load: float, spd: float, state: str, sim: BuildingSimulator,
) -> float:
    # Standby / door operation power
    if state == "IDLE":
        return 0.3
    if state in ("DOOR_OPENING", "DOOR_CLOSING"):
        return 1.0
    if state == "DOORS_OPEN":
        return 0.3

    speed = abs(spd)
    if speed < 0.01:
        return 1.0

    total_cabin_mass = CABIN_EMPTY_MASS + load
    unbalance_force = (total_cabin_mass - COUNTERWEIGHT_MASS) * G
    direction = sim._elev_direction

    if direction * unbalance_force > 0:
        motor_force = unbalance_force
    else:
        motor_force = 0.0

    total_system_mass = total_cabin_mass + COUNTERWEIGHT_MASS
    inertial_force = total_system_mass * abs(sim._elev_current_accel)
    motor_force += inertial_force

    mechanical_power = motor_force * speed
    electrical_power = mechanical_power / MOTOR_EFFICIENCY / 1000

    if sim._elev_current_accel < 0:
        electrical_power *= 0.2

    friction_loss = speed * 200 / 1000
    auxiliary = 0.5

    return max(0.0, electrical_power) + friction_loss + auxiliary


def _check_motor_stuck(
    sim: BuildingSimulator, state: str, speed: float,
    load: float, temperature: float, dt: float,
) -> bool:
    if state in ("IDLE", "DOOR_OPENING", "DOORS_OPEN", "DOOR_CLOSING"):
        sim._elev_stuck_timer = 0.0
        return False
    from apps.sensors.simulation.constants import (
        ELEVATOR_LOAD_ALERT, ELEVATOR_TEMP_ALERT,
        STUCK_THRESHOLD_TICKS, STUCK_SPEED_EPSILON,
    )
    if abs(speed) < STUCK_SPEED_EPSILON and (
        load > ELEVATOR_LOAD_ALERT
        or temperature > ELEVATOR_TEMP_ALERT
        or sim._elev_motor_torque_factor <= 0
    ):
        sim._elev_stuck_timer += dt
    else:
        sim._elev_stuck_timer = 0.0
    return sim._elev_stuck_timer >= STUCK_THRESHOLD_TICKS
