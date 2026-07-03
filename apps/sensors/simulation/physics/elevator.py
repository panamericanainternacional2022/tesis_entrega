import random
import time

from apps.sensors.sensor_config import SENSOR_RANGES, ELEVATOR_VARS
from apps.sensors.simulation.constants import (
    T_AMBIENT, FLOOR_HEIGHT,
    CRUISING_SPEED, ACCELERATION, PASSENGER_WAIT_TICKS,
)
from apps.sensors.simulation.models import BuildingSimulator

_LOAD_LOW, _LOAD_HIGH = SENSOR_RANGES["load"]
_ENERGY_LOW, _ENERGY_HIGH = SENSOR_RANGES["energy"]
_TEMP_LOW, _TEMP_HIGH = SENSOR_RANGES["temperature"]
_SPEED_LOW, _SPEED_HIGH = SENSOR_RANGES["speed"]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _is_locked(sim: BuildingSimulator, var: str) -> bool:
    if hasattr(sim, "manual_overrides") and isinstance(sim.manual_overrides, dict):
        return time.time() < sim.manual_overrides.get(var, 0)
    return False


def _update_elevator(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed
    if not sim.elevator_on or "elevator" in sim.protection_ends:
        _set_elevator_idle(sim, sd, dt)
        return
    if "elevator" in sim.sim_faults:
        _apply_elevator_fault(sim, sd, dt)
        return
    _run_elevator_fsm(sim, sd, dt)


def _set_elevator_idle(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    if not _is_locked(sim, "speed"):
        sd["speed"] = _clamp(sd.get("speed", 0.0) - 1.0 * dt, _SPEED_LOW, _SPEED_HIGH)
    if not _is_locked(sim, "load"):
        sd["load"] = int(max(0, sd["load"] - 50 * dt))
    if not _is_locked(sim, "door_status"):
        sd["door_status"] = "closed"
    if not _is_locked(sim, "energy"):
        sd["energy"] = round(_clamp(sd.get("energy", 0) - 0.3 * dt, _ENERGY_LOW, _ENERGY_HIGH), 1)
    if not _is_locked(sim, "motor_stuck"):
        sd["motor_stuck"] = False
    sim.door_close_attempts = 0
    sim._elev_state = "IDLE"


def _apply_elevator_fault(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    fault_type = sim.sim_faults.get("elevator")
    temp_sd = sd.copy()
    
    _ELEV_FAULT_HANDLERS = {
        "motor_stuck":        _apply_motor_stuck,
        "door_blocked":       _apply_door_blocked,
        "door_close_failure": _apply_door_close_failure,
        "overspeed":          _apply_overspeed,
    }
    handler = _ELEV_FAULT_HANDLERS.get(fault_type)
    if handler:
        handler(sim, temp_sd, dt)
        
    for k in ELEVATOR_VARS:
        if not _is_locked(sim, k):
            sd[k] = temp_sd[k]


def _apply_motor_stuck(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sd["speed"] = _clamp(sd.get("speed", 0.0) - 1.5 * dt, _SPEED_LOW, _SPEED_HIGH)
    sd["motor_stuck"] = True
    sd["door_status"] = "closed"
    sd["energy"] = round(_clamp(sd.get("energy", 0) + 1.0 * dt, _ENERGY_LOW, _ENERGY_HIGH), 1)
    sd["temperature"] = _clamp(sd.get("temperature", 50.0) + 1.5 * dt, _TEMP_LOW, _TEMP_HIGH)


def _apply_door_blocked(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sd["door_status"] = "open"
    sim.door_close_attempts += 1
    sd["motor_stuck"] = False
    sd["speed"] = _clamp(sd.get("speed", 0.0) - 1.5 * dt, _SPEED_LOW, _SPEED_HIGH)
    sd["energy"] = round(_clamp(sd.get("energy", 0) - 0.5 * dt, _ENERGY_LOW, _ENERGY_HIGH), 1)


def _apply_door_close_failure(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    """Puerta falla al cerrar gradualmente: 1 intento cada ~3 s.

    Simula el escenario donde el elevador está parado en un piso pero la
    puerta no cierra correctamente.  Fuerza speed=0 y estado IDLE para que
    ``is_moving`` sea False en el alert handler, permitiendo que el badge
    muestre "Puerta: intento X/2" antes de disparar la alerta de modo seguro.
    """
    # Elevador detenido en piso: no está en movimiento
    sd["speed"] = 0.0
    sd["door_status"] = "open"
    sd["motor_stuck"] = False
    sd["energy"] = round(_clamp(sd.get("energy", 0) - 0.2 * dt, _ENERGY_LOW, _ENERGY_HIGH), 1)
    sim._elev_state = "IDLE"
    # Acumular tiempo; cada 3 segundos registrar un intento fallido de cierre
    sim._elev_timer = getattr(sim, "_elev_timer", 0) + dt
    if sim._elev_timer >= 3.0:
        sim._elev_timer = 0.0
        sim.door_close_attempts += 1


def _apply_overspeed(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sd["speed"] = _clamp(sd["speed"] + 0.5 * dt, _SPEED_LOW, _SPEED_HIGH)
    direction = getattr(sim, "_elev_direction", 1)
    sim._elev_position_meters = _clamp(
        sim._elev_position_meters + sd["speed"] * dt * direction, 0, sim.floors * FLOOR_HEIGHT,
    )
    sd["position"] = round(sim._elev_position_meters / FLOOR_HEIGHT, 1)
    sd["door_status"] = "closed"
    sd["motor_stuck"] = False
    sd["load"] = _clamp(sd["load"] + random.uniform(-10, 10) * dt, _LOAD_LOW, _LOAD_HIGH)
    load_imbalance = abs(sd["load"] - 400) / 400
    sd["energy"] = 1.5 + load_imbalance * sd["speed"] * 1.5


def _run_elevator_fsm(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    # Emergency stop / safety interlock check:
    # If the door is not closed, the elevator must not be moving.
    # If it is in a moving state and doors are not closed, force an emergency stop and open doors!
    is_moving_state = sim._elev_state in ("ACCELERATING", "MOVING", "DECELERATING")
    if is_moving_state and sd.get("door_status") != "closed":
        sd["speed"] = 0.0
        sim._elev_state = "DOOR_OPENING"
        sim._elev_timer = 0.0

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
    if sim._elev_timer >= random.uniform(2, 5):
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
    if sim._elev_timer >= 1:
        sim._elev_timer = 0
        if not _is_locked(sim, "load"):
            # Keep load within normal limits [0, 500] kg
            load = _clamp(load + random.randint(-150, 150), 0, 500)
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
        if not _is_locked(sim, "load"):
            # Keep load within normal limits [0, 500] kg
            load = _clamp(load + random.randint(-150, 150), 0, 500)
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
    
    if load > 900:
        sim._elev_state = "DOOR_OPENING"
        sim._elev_timer = 0
        sd["door_status"] = "open"
        sd["speed"] = 0.0
        sim.door_close_attempts += 1
        return

    if sim._elev_timer >= 1:
        from apps.sensors.simulation.constants import MAX_DOOR_CLOSE_ATTEMPTS
        is_locked_open = _is_locked(sim, "door_status") and sd.get("door_status") != "closed"
        random_fail = random.random() < 0.02 * dt
        
        if is_locked_open or random_fail:
            sim.door_close_attempts += 1
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
            sd["door_status"] = "closed"
            sd["speed"] = 0.0
            return


def _handle_elev_accelerating(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = _clamp(spd + ACCELERATION * dt, 0, CRUISING_SPEED)
    door = "closed"
    pos += spd * direction * 0.5 * dt
    if spd >= CRUISING_SPEED * 0.9:
        sim._elev_state = "MOVING"
    sd["speed"] = spd
    sd["door_status"] = door
    sim._elev_position_meters = pos


def _handle_elev_moving(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = CRUISING_SPEED + random.uniform(-0.1, 0.1) * dt
    door = "closed"
    pos += spd * direction * dt
    if direction > 0 and pos >= target - 1.5:
        sim._elev_state = "DECELERATING"
        sim._elev_timer = 0
    elif direction < 0 and pos <= target + 1.5:
        sim._elev_state = "DECELERATING"
        sim._elev_timer = 0
    sd["speed"] = spd
    sd["door_status"] = door
    sim._elev_position_meters = pos


def _handle_elev_decelerating(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = _clamp(spd - ACCELERATION * dt, 0, CRUISING_SPEED)
    door = "closed"
    pos += spd * direction * 0.5 * dt
    if spd <= 0.05:
        spd = 0.0
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
        sim._elev_timer = 0
        sim._elev_state = "DOOR_OPENING"
        sim._elev_at_floor = True
    sd["speed"] = spd
    sd["door_status"] = door
    sim._elev_position_meters = pos


def _run_elevator_post_fsm(
    sim: BuildingSimulator, sd: dict, dt: float,
    prev_pos: float, spd: float,
    load: float, door: str, old_state: str,
) -> None:
    pos = _clamp(sim._elev_position_meters, 0, sim.floors * FLOOR_HEIGHT)
    sim._elev_position_meters = pos
    current_state = sim._elev_state
    if current_state in ("IDLE", "DOOR_OPENING", "DOORS_OPEN", "DOOR_CLOSING"):
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
        sim._elev_position_meters = pos
    if spd != 0:
        sim.door_close_attempts = 0
    if current_state == "DOOR_CLOSING" and sim._elev_timer >= 1:
        if random.random() < 0.15 * dt:
            sim.door_close_attempts += 1
    
    moving_states = {"ACCELERATING", "MOVING", "DECELERATING"}
    if old_state in moving_states and current_state not in moving_states:
        if not _is_locked(sim, "trip_count"):
            sd["trip_count"] += 1
        
    energy = _compute_elevator_energy(load, spd, current_state, sim)
    stuck = _check_motor_stuck(current_state, spd, load, sd.get("temperature", 50.0))
    
    if not _is_locked(sim, "position"):
        sd["position"] = round(sim._elev_position_meters / FLOOR_HEIGHT, 1)
    if not _is_locked(sim, "speed"):
        sd["speed"] = round(spd, 1)
    if not _is_locked(sim, "load"):
        sd["load"] = round(load)
    if not _is_locked(sim, "door_status"):
        sd["door_status"] = door
    if not _is_locked(sim, "energy"):
        sd["energy"] = round(_clamp(energy, _ENERGY_LOW, _ENERGY_HIGH), 1)
    if not _is_locked(sim, "motor_stuck"):
        sd["motor_stuck"] = stuck
        
    sim._elev_prev_position = prev_pos


def _compute_elevator_energy(
    load: float, spd: float, state: str, sim: BuildingSimulator,
) -> float:
    if state == "IDLE":
        return 0.5
    if state in ("DOOR_OPENING", "DOOR_CLOSING"):
        return 1.5
    if state == "DOORS_OPEN":
        return 0.8

    load_imbalance = abs(load - 400) / 400
    base_power = 1.5 + load_imbalance * spd * 1.5

    if state == "ACCELERATING":
        return base_power * 1.3
    if state == "DECELERATING":
        return max(0.2, base_power * 0.3)
    return base_power


def _check_motor_stuck(state: str, speed: float, load: float, temperature: float) -> bool:
    if state in ("IDLE", "DOOR_OPENING", "DOORS_OPEN", "DOOR_CLOSING"):
        return False
    from apps.sensors.simulation.constants import ELEVATOR_LOAD_ALERT, ELEVATOR_TEMP_ALERT
    return speed == 0 and (load > ELEVATOR_LOAD_ALERT or temperature > ELEVATOR_TEMP_ALERT)
