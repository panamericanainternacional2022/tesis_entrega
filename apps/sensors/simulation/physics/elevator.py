import random

from apps.sensors.sensor_config import ENUM_VARS, DEFAULT_THRESHOLDS
from apps.sensors.simulation.constants import (
    FLOOR_HEIGHT,
    CRUISING_SPEED, ACCELERATION, PASSENGER_WAIT_TICKS,
    JERK, G, CABIN_EMPTY_MASS, COUNTERWEIGHT_MASS, MOTOR_EFFICIENCY,
    DOOR_OPEN_TIME, DOOR_CLOSE_TIME, RATED_LOAD,
    OVERLOAD_EXTRA_KG,
    POWER_OUTAGE_BRAKE_TIME, POWER_OUTAGE_BATTERY_WAIT,
    BATTERY_RESCUE_SPEED,
    OVERSPEED_GOVERNOR_TRIGGER, OVERSPEED_ACCEL_RATE,
    ELEVATOR_MOTOR_TEMP_AMBIENT,
    ELEVATOR_MOTOR_RATED_CURRENT,
    ELEVATOR_LOCKED_ROTOR_CURRENT,
    ELEVATOR_DOOR_MOTOR_CURRENT,
    ELEVATOR_BRAKE_SHOCK_VIBRATION,
    SAFETY_GOVERNOR_TRIP_SPEED,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.utils import clamp


# Umbral de bloqueo físico por sobrecarga - derivado de DEFAULT_THRESHOLDS para
# que cada edificio con sus propios umbrales refleje el bloqueo correcto (spec: >800 kg)

# ── Tasas de ramping progresivo por variable (unidades por tick) ──
# Alineadas con las tasas de cambio en operación normal para transiciones coherentes.
ELEV_RAMP_RATES = {
    "elev_speed":       0.5,   # m/s/tick  — Igual a ramp normal (accel ~0.5)
    "elev_current":     3.0,   # A/tick    — Coherente con ramp normal (~3 A)
    "elev_temperature": 1.0,   # °C/tick   — Inercia térmica realista (normal ~0.3)
    "elev_vibration":   2.0,   # mm/s/tick — Igual a ramp normal
    "elev_voltage":    15.0,   # V/tick    — Rápido pero no instantáneo (red tiene impedancia)
    "elev_load":       100.0,  # kg/tick   — Pasajeros (instantáneo en la realidad)
    "elev_position":    1.0,   # pisos/tick
}


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
    sim._elev_power_available = True
    sim._elev_brake_failed = False
    sim._elev_power_outage_timer = 0.0
    sim._elev_power_outage_complete = False
    sim._elev_traction_loss = False
    sim._elev_governor_tripped = False


def _check_safety_chain(sim: BuildingSimulator, sd: dict) -> bool:
    """
    Verifica la Cadena de Seguridad (contactos de seguridad en serie:
    puertas DW/GS, limitador de velocidad, corte de energía y sobrecarga).
    Retorna True si la cadena permite energización del motor de tracción.
    """
    door_status = sd.get("elev_door_status", "closed")
    door_ok = (door_status in ("closed", "closing")) and not getattr(sim, "_elev_door_obstructed", False)
    power_ok = getattr(sim, "_elev_power_available", True)
    governor_ok = not getattr(sim, "_elev_speed_governor_failed", False) or not getattr(sim, "_elev_governor_tripped", False)
    
    total_load = _effective_load(sim, sd.get("elev_load", 0))
    overload_ok = (total_load <= RATED_LOAD * 1.10) and (getattr(sim, "_elev_overload_extra_kg", 0) <= 0)
    
    return door_ok and power_ok and governor_ok and overload_ok


# ---------------------------------------------------------------------------
#  FAULT PARAM SETTERS
# ---------------------------------------------------------------------------

def _set_motor_stuck_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sim._elev_motor_torque_factor = 0.0


def _set_door_blocked_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sim._elev_door_obstructed = True


def _set_overspeed_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sim._elev_speed_governor_failed = True
    sim._elev_brake_failed = True


def _set_overload_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sim._elev_overload_extra_kg = OVERLOAD_EXTRA_KG


def _set_power_outage_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sim._elev_power_available = False
    sim._elev_motor_torque_factor = 0.0


def _set_traction_loss_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sim._elev_traction_loss = True


# ---------------------------------------------------------------------------
#  MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def _snapshot_protected_values(sim: BuildingSimulator, sd: dict) -> dict:
    protected: dict = {}

    fault = sim.sim_faults.get("elevator") if hasattr(sim, "sim_faults") else None
    if fault:
        for var in _get_fault_telemetry_targets(sim, fault):
            protected[var] = sd.get(var)

    return protected


def _restore_protected(sd: dict, protected: dict) -> None:
    for var, val in protected.items():
        if val is not None:
            sd[var] = val


def _update_elevator(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed
    # Recovery countdown (debe ejecutarse incluso con elevador apagado)
    if sim.fault_transition_elev == "recovering":
        sim._fault_transition_ticks_elev -= 1
        if sim._fault_transition_ticks_elev <= 0:
            sim.fault_transition_elev = "stable"

    if not sim.elevator_on:
        _set_elevator_idle(sim, sd, dt)
        _clear_elevator_fault_params(sim)
        return

    protected = _snapshot_protected_values(sim, sd)

    if "elevator" in sim.sim_faults:
        _apply_elevator_fault_params(sim, sd, dt)
    else:
        _clear_elevator_fault_params(sim)

    # ── Safety Chain Interlock Check ──────────────────────────────────────
    if not _check_safety_chain(sim, sd):
        if sim._elev_state in ("ACCELERATING", "MOVING", "DECELERATING"):
            sim._elev_state = "IDLE"
            sd["elev_speed"] = 0.0
            sd["elev_current"] = 0.0
            sim._elev_motor_torque_factor = 0.0

    _run_elevator_fsm(sim, sd, dt)

    _restore_protected(sd, protected)

    if "elevator" in sim.sim_faults:
        _force_elevator_fault_telemetry(sim, sd)
        # Sincronizar estado térmico interno con la temperatura forzada por la falla
        # para evitar que el modelo térmico del post_fsm contradiga el valor forzado
        sim._elev_motor_temp = sd.get("elev_temperature", sim._elev_motor_temp)


def _get_fault_telemetry_targets(sim: BuildingSimulator, fault: str) -> dict:
    # ── Carga umbrales dinámicos del edificio ──────────────────────────────
    try:
        from apps.thresholds.services import get_thresholds
        thresh = get_thresholds(sim.edificio_id)
    except Exception:
        thresh = {}

    def _critic(var: str, default: float) -> float:
        return thresh.get(var, {}).get("critic", default)

    def _high(var: str, default: float) -> float:
        return thresh.get(var, {}).get("high", default)

    lim = sim.sensor_limits

    def _above(var: str, default_critic: float, factor: float = 1.1) -> float:
        return min(lim.get(var, (0.0, 9999.0))[1], _critic(var, default_critic) * factor)

    targets = {
        "motor_stuck": {
            "elev_speed": 0.0,
            # Pico de Rotor Bloqueado (LRA) instantáneo
            "elev_current": ELEVATOR_LOCKED_ROTOR_CURRENT,
            "elev_door_status": "closed",
            # Temperatura sube térmicamente por I^2*R
            "elev_temperature": _above("elev_temperature", 75.0, 1.1),
            "elevator_state": "STUCK",
            # Vibración por zumbido electromagnético intenso de rotor bloqueado
            "elev_vibration": _above("elev_vibration", 5.0, 1.15),
            "elev_voltage": 340.0,  # Caída de tensión por sobrecorriente de rotor bloqueado
        },
        "door_blocked": {
            "elev_door_status": "blocked",
            "elev_speed": 0.0,
            "elev_current": ELEVATOR_DOOR_MOTOR_CURRENT,  # Corriente del operador de puerta, tracción = 0 A
            "elevator_state": "DOORS_OPEN",
        },
        "overspeed": {
            "elev_speed": 0.0 if getattr(sim, "_elev_governor_tripped", False) else _above("elev_speed", 1.6, 1.15),
            "elev_current": 0.0 if getattr(sim, "_elev_governor_tripped", False) else _high("elev_current", 10.0),
            "elev_door_status": "closed",
            "elev_vibration": 12.0 if getattr(sim, "_elev_governor_tripped", False) else _above("elev_vibration", 5.0, 1.1),
            "elevator_state": "SAFETY_GEAR_TRIPPED" if getattr(sim, "_elev_governor_tripped", False) else "MOVING",
        },
        "overload": {
            "elev_load": _above("elev_load", 800.0, 1.05),
            "elev_door_status": "open",
            "elev_speed": 0.0,
            # Corriente de standby: circuitos de control, iluminación cabina, operador de puerta
            "elev_current": ELEVATOR_MOTOR_RATED_CURRENT * 0.08,
            # Motor NO energizado → temperatura se mantiene en ambiente
            "elev_temperature": ELEVATOR_MOTOR_TEMP_AMBIENT,
            "elevator_state": "DOORS_OPEN",
        },
        "traction_loss": {
            # Vibración alta por fricción de rozamiento de cables en garganta
            "elev_vibration": _above("elev_vibration", 5.0, 1.15),
            # Corriente de marcha en vacío (~20% nominal)
            "elev_current": ELEVATOR_MOTOR_RATED_CURRENT * 0.2,
            # CORRECCIÓN TERMODINÁMICA: Motor en vacío disipa muy poco calor (I^2 * R = 4% de la nominal)
            "elev_temperature": ELEVATOR_MOTOR_TEMP_AMBIENT + 8.0,
            "elev_speed": CRUISING_SPEED,
        }
    }
    if fault == "commercial_power_outage":
        timer = getattr(sim, "_elev_power_outage_timer", 0.0)
        complete = getattr(sim, "_elev_power_outage_complete", False)
        dt = sim.sim_speed or 1.0
        if complete:
            return {
                "elev_speed": 0.0,
                "elev_voltage": 0.0,
                "elev_door_status": "open",
                "elev_current": 0.0,
                "elev_temperature": ELEVATOR_MOTOR_TEMP_AMBIENT,
                "elev_vibration": 0.0,
                # E-7: Pasajeros evacuan con puerta abierta tras rescate completado
                "elev_load": 0,
                "elevator_state": "DOORS_OPEN",
            }
        elif timer <= max(POWER_OUTAGE_BRAKE_TIME, dt):
            return {
                "elev_speed": 0.0,
                "elev_voltage": 0.0,
                "elev_door_status": "closed",
                "elev_current": 0.0,
                "elev_vibration": ELEVATOR_BRAKE_SHOCK_VIBRATION,
            }
        elif timer < POWER_OUTAGE_BATTERY_WAIT:
            return {
                "elev_speed": 0.0,
                "elev_voltage": 0.0,
                "elev_door_status": "closed",
                "elev_current": 0.0,
                "elev_vibration": 0.2,
                "elevator_state": "IDLE",
            }
        else:
            return {
                "elev_speed": BATTERY_RESCUE_SPEED,
                "elev_voltage": 48.0,
                "elev_door_status": "closed",
                "elev_current": ELEVATOR_MOTOR_RATED_CURRENT * 0.15,
                "elev_vibration": 0.5,
                "elevator_state": "MOVING",
            }
    return targets.get(fault, {})


def _ramp_toward_target(sd: dict, var: str, target, rate: float, dt: float) -> bool:
    current = sd.get(var)
    if current is None:
        sd[var] = target
        return True

    try:
        t = float(target)
        c = float(current)
    except (ValueError, TypeError):
        sd[var] = target
        return True

    diff = abs(t - c)
    if diff < 0.1:
        sd[var] = target
        return True
    step = rate * dt
    if diff <= step:
        sd[var] = target
        return True

    sd[var] = c + step if t > c else c - step
    return False


STEP_VARS_BY_FAULT = {
    "commercial_power_outage": {"elev_voltage", "elev_current", "elev_vibration", "elev_speed", "elev_door_status"},
    "motor_stuck": {"elev_current", "elev_voltage", "elev_vibration", "elev_speed", "elev_door_status"},
    "door_blocked": {"elev_current", "elev_speed", "elev_door_status"},
    "overload": {"elev_load", "elev_current", "elev_speed", "elev_door_status", "elev_temperature"},
    "traction_loss": {"elev_current", "elev_temperature"},
    "overspeed": {"elev_speed", "elev_vibration", "elev_current"},
}


def _force_elevator_fault_telemetry(sim: BuildingSimulator, sd: dict) -> None:
    fault = sim.sim_faults.get("elevator")
    if not fault:
        return

    targets = _get_fault_telemetry_targets(sim, fault)
    dt = sim.sim_speed or 1.0
    step_vars = STEP_VARS_BY_FAULT.get(fault, set())

    all_reached = True
    for var, target in targets.items():
        if var in ENUM_VARS or isinstance(target, str) or var in step_vars:
            if isinstance(target, (int, float)):
                if var in ("elev_load",):
                    sd[var] = int(round(target))
                else:
                    sd[var] = round(target, 1)
            else:
                sd[var] = target
            continue

        bounds = sim.sensor_limits.get(var)
        if bounds and isinstance(target, (int, float)):
            target = max(bounds[0], min(bounds[1], target))

        rate = ELEV_RAMP_RATES.get(var, 2.0)
        if not _ramp_toward_target(sd, var, target, rate, dt):
            all_reached = False

        val = sd[var]
        if var in ("elev_load",):
            val = int(round(val))
        elif isinstance(val, (int, float)):
            val = round(val, 1)
        sd[var] = val

    sim.fault_transition_elev = "stable" if all_reached else "injecting"


def _set_elevator_idle(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    _ramp_toward_target(sd, "elev_speed", 0.0, ELEV_RAMP_RATES.get("elev_speed", 0.5), dt)
    _ramp_toward_target(sd, "elev_voltage", 380.0, ELEV_RAMP_RATES.get("elev_voltage", 30.0), dt)
    _ramp_toward_target(sd, "elev_vibration", 0.5, ELEV_RAMP_RATES.get("elev_vibration", 2.0), dt)
    _ramp_toward_target(sd, "elev_current", 0.0, ELEV_RAMP_RATES.get("elev_current", 4.0), dt)
    sd["elev_load"] = int(max(0, sd["elev_load"] - 50 * dt))
    sim._elev_motor_temp += (ELEVATOR_MOTOR_TEMP_AMBIENT - sim._elev_motor_temp) * 0.05 * dt
    sd["elev_temperature"] = round(clamp(sim._elev_motor_temp, ELEVATOR_MOTOR_TEMP_AMBIENT, sim.sensor_limits.get('elev_temperature', (22.0, 90.0))[1]), 1)
    sim._elev_state = "IDLE"
    sim._elev_current_accel = 0.0
    sim._elev_timer = 5.0


def _apply_elevator_fault_params(sim: BuildingSimulator, sd: dict, dt: float) -> None:
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
        "commercial_power_outage": _set_power_outage_params,
        "traction_loss":           _set_traction_loss_params,
    }
    handler = _ELEV_FAULT_PARAM_SETTERS.get(fault_type)
    if handler:
        handler(sim, sd, dt)


# ---------------------------------------------------------------------------
#  POWER OUTAGE HANDLER
# ---------------------------------------------------------------------------

def _handle_power_outage_fsm(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float,
) -> None:
    if sim._elev_power_outage_complete:
        sd["elev_speed"] = 0.0
        sd["elev_door_status"] = "open"
        return

    sim._elev_power_outage_timer += dt
    timer = sim._elev_power_outage_timer

    if timer < POWER_OUTAGE_BRAKE_TIME:
        spd = max(0.0, spd - 2.5 * dt)
        sd["elev_speed"] = round(spd, 1)
        sd["elev_door_status"] = "closed"
        sim._elev_position_meters = clamp(
            sim._elev_position_meters + spd * sim._elev_direction * dt,
            0, sim.floors * FLOOR_HEIGHT,
        )
        sd["elev_position"] = round(sim._elev_position_meters / FLOOR_HEIGHT, 1)
        if spd <= 0.01:
            sim._elev_state = "IDLE"
        return

    if timer < POWER_OUTAGE_BATTERY_WAIT:
        spd = 0.0
        sd["elev_speed"] = 0.0
        sd["elev_door_status"] = "closed"
        sim._elev_state = "IDLE"
        return

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
    sd["elev_position"] = round(sim._elev_position_meters / FLOOR_HEIGHT, 1)
    sd["elev_speed"] = round(spd, 1)
    sd["elev_door_status"] = "closed"

    if abs(sim._elev_position_meters - target_m) < 0.3:
        sd["elev_speed"] = 0.0
        sd["elev_door_status"] = "open"
        sim._elev_state = "DOORS_OPEN"
        sim._elev_power_outage_complete = True


# ---------------------------------------------------------------------------
#  ELEVATOR FSM
# ---------------------------------------------------------------------------

def _run_elevator_fsm(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    is_moving_state = sim._elev_state in ("ACCELERATING", "MOVING", "DECELERATING")
    if is_moving_state and sd.get("elev_door_status") != "closed" and sd.get("elev_door_status") != "closing":
        sd["elev_speed"] = 0.0
        if sim._elev_state != "DOOR_OPENING":
            sim._elev_state = "DOOR_OPENING"
            sim._elev_timer = 0.0

    if not sim._elev_power_available:
        prev_pos = sim._elev_position_meters
        spd = sd.get("elev_speed", 0.0)
        pos = sim._elev_position_meters
        load = sd.get("elev_load", 0)
        _state_before_outage = sim._elev_state
        _handle_power_outage_fsm(sim, sd, dt, spd, pos, load)
        _run_elevator_post_fsm(
            sim, sd, dt, prev_pos,
            sd.get("elev_speed", 0.0), sd.get("elev_load", 0),
            sd.get("elev_door_status", "closed"), _state_before_outage,
        )
        return

    sim._elev_timer += dt
    prev_pos = sim._elev_position_meters
    pos = sim._elev_position_meters
    spd = sd["elev_speed"]
    load = sd["elev_load"]
    door = sd["elev_door_status"]
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
    spd = sd["elev_speed"]
    door = sd["elev_door_status"]
    load = sd["elev_load"]
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
    sd["elev_speed"] = spd
    sd["elev_door_status"] = door


def _handle_elev_door_opening(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "opening"
    if sim._elev_timer >= DOOR_OPEN_TIME:
        sim._elev_timer = 0
        sim._elev_state = "DOORS_OPEN"
    sd["elev_speed"] = spd
    sd["elev_door_status"] = door
    sd["elev_load"] = round(load)


def _handle_elev_doors_open(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "open"

    total_load = _effective_load(sim, load)
    try:
        from apps.thresholds.services import get_thresholds
        _t = get_thresholds(sim.edificio_id)
        critic_load = _t.get("elev_load", {}).get("critic", DEFAULT_THRESHOLDS.get("elev_load", {}).get("critic", 800.0))
    except Exception:
        critic_load = DEFAULT_THRESHOLDS.get("elev_load", {}).get("critic", 800.0)
    if total_load > critic_load:
        sim._elev_timer = 0
        if sim._elev_overload_extra_kg <= 0:
            load = max(0, load - 150 * dt)
        sd["elev_speed"] = spd
        sd["elev_door_status"] = door
        sd["elev_load"] = round(load)
        return

    if sim._elev_timer >= PASSENGER_WAIT_TICKS:
        sim._elev_timer = 0
        normal_max = int(RATED_LOAD * 1.1)
        load = clamp(load + random.randint(-150, 150), 0, normal_max)
        sim._elev_state = "DOOR_CLOSING"
    sd["elev_speed"] = spd
    sd["elev_door_status"] = door
    sd["elev_load"] = round(load)


def _handle_elev_door_closing(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:

    total_load = _effective_load(sim, load)
    # Bloqueo físico según el umbral crítico de carga configurado por el usuario
    try:
        from apps.thresholds.services import get_thresholds
        _t = get_thresholds(sim.edificio_id)
        critic_load = _t.get("elev_load", {}).get("critic", DEFAULT_THRESHOLDS.get("elev_load", {}).get("critic", 800.0))
    except Exception:
        critic_load = DEFAULT_THRESHOLDS.get("elev_load", {}).get("critic", 800.0)
    if total_load > critic_load:
        sim._elev_state = "DOOR_OPENING"
        sim._elev_timer = 0
        sd["elev_door_status"] = "open"
        sd["elev_speed"] = 0.0
        sd["elev_current"] = 0.0   # Spec: motor bloqueado → current = 0.0
        return
        
    # Lógica de cierre normal
    if sim._elev_timer >= DOOR_CLOSE_TIME:
        door_obstructed = sim._elev_door_obstructed
        overload_fault_active = (
            sim._elev_overload_extra_kg > 0
            and total_load > RATED_LOAD * 1.0
        )
        random_fail = random.random() < 0.02 * dt

        if door_obstructed or overload_fault_active or random_fail:
            if door_obstructed or overload_fault_active:
                sim._elev_state = "DOORS_OPEN"
                sim._elev_timer = 0
                sd["elev_door_status"] = "open"
                sd["elev_speed"] = 0.0
                return
            else:
                sim._elev_state = "DOOR_OPENING"
                sim._elev_timer = 0
                sd["elev_door_status"] = "opening"
                sd["elev_speed"] = 0.0
                return

        floor_num = round(pos / FLOOR_HEIGHT)
        if floor_num == sim._elev_target_floor:
            sim._elev_timer = 0
            sim._elev_state = "IDLE"
            sd["elev_door_status"] = "closed"
            sd["elev_speed"] = 0.0
            return
        else:
            sim._elev_timer = 0
            sim._elev_state = "ACCELERATING"
            sim._elev_current_accel = 0
            sd["elev_door_status"] = "closed"
            sd["elev_speed"] = 0.0
            return


def _handle_elev_accelerating(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    prev_spd = spd
    if sim._elev_motor_torque_factor <= 0:
        sim._elev_state = "MOVING"
        sim._elev_current_accel = 0.0
        sd["elev_speed"] = 0.0
        sd["elev_door_status"] = "closed"
        sim._elev_position_meters = pos
        return

    effective_jerk = JERK * sim._elev_motor_torque_factor
    max_accel = ACCELERATION * sim._elev_motor_torque_factor
    sim._elev_current_accel = min(
        sim._elev_current_accel + effective_jerk * dt,
        max(0, max_accel),
    )
    speed_cap = CRUISING_SPEED if not sim._elev_speed_governor_failed else CRUISING_SPEED * 3
    spd = clamp(spd + sim._elev_current_accel * dt, 0, speed_cap)
    door = "closed"
    
    pos_change_factor = 0.1 if getattr(sim, "_elev_traction_loss", False) else 1.0
    pos += (prev_spd + spd) / 2 * direction * dt * pos_change_factor
    
    if spd >= CRUISING_SPEED * 0.9 and not sim._elev_speed_governor_failed:
        sim._elev_state = "MOVING"
        sim._elev_current_accel = 0.0
    elif spd >= speed_cap * 0.9:
        sim._elev_state = "MOVING"
        sim._elev_current_accel = 0.0
    sd["elev_speed"] = spd
    sd["elev_door_status"] = door
    sim._elev_position_meters = pos


def _handle_elev_moving(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    door = "closed"

    if sim._elev_speed_governor_failed and sim._elev_motor_torque_factor > 0:
        spd = spd + OVERSPEED_ACCEL_RATE * dt
        if spd > CRUISING_SPEED * OVERSPEED_GOVERNOR_TRIGGER and not sim._elev_brake_failed:
            spd = 0.0
            sim._elev_state = "IDLE"
            sim._elev_timer = 0
            sd["elev_speed"] = spd
            sd["elev_door_status"] = door
            sim._elev_position_meters = pos
            sd["elev_position"] = round(pos / FLOOR_HEIGHT, 1)
            return
    elif sim._elev_motor_torque_factor <= 0:
        spd = max(0.0, spd - 1.5 * dt)
        if spd <= 0.01:
            spd = 0.0
            sim._elev_state = "IDLE"
            sim._elev_timer = 0
    else:
        target_spd = CRUISING_SPEED + random.uniform(-0.1, 0.1) * dt
        if spd > target_spd:
            spd = max(target_spd, spd - 0.5 * dt)
        elif spd < target_spd - 0.2:
            spd = min(target_spd, spd + 0.5 * dt)
        else:
            spd = target_spd

    pos_change_factor = 0.1 if getattr(sim, "_elev_traction_loss", False) else 1.0
    pos += spd * direction * dt * pos_change_factor
    stopping_distance = (spd ** 2) / (2 * ACCELERATION) + 0.5
    if direction > 0 and pos >= target - stopping_distance:
        sim._elev_state = "DECELERATING"
        sim._elev_timer = 0
        sim._elev_current_accel = 0
    elif direction < 0 and pos <= target + stopping_distance:
        sim._elev_state = "DECELERATING"
        sim._elev_timer = 0
        sim._elev_current_accel = 0
    sd["elev_speed"] = spd
    sd["elev_door_status"] = door
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
    pos_change_factor = 0.1 if getattr(sim, "_elev_traction_loss", False) else 1.0
    pos += (prev_spd + spd) / 2 * direction * dt * pos_change_factor
    if spd <= 0.05:
        spd = 0.0
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
        sim._elev_timer = 0
        sim._elev_state = "DOOR_OPENING"
        sim._elev_current_accel = 0
    elif sim._elev_speed_governor_failed and (pos >= sim.floors * FLOOR_HEIGHT or pos <= 0):
        spd = 0.0
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
        sim._elev_timer = 0
        sim._elev_state = "IDLE"
        sim._elev_current_accel = 0
    sd["elev_speed"] = spd
    sd["elev_door_status"] = door
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
    if current_state in ("IDLE", "DOOR_OPENING", "DOORS_OPEN", "DOOR_CLOSING") and sim._elev_power_available:
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
        sim._elev_position_meters = pos

    effective_load = _effective_load(sim, load)

    # ── Position sensor ────────────────────────────────────────────────────
    sd["elev_position"] = round(sim._elev_position_meters / FLOOR_HEIGHT, 1)

    # ── Power outage forces current to 0 ───────────────────────────────────
    if not sim._elev_power_available:
        sd["elev_current"] = 0.0

    # ── Elevator motor temperature simulation ──────────────────────────────
    from apps.thresholds.services import get_thresholds
    thresh = get_thresholds(sim.edificio_id)
    temp_high = thresh.get("elev_temperature", {}).get("high", 60.0)
    safe_temp_max = temp_high * 0.95

    if not sim._elev_power_outage_complete:
        target_temp = ELEVATOR_MOTOR_TEMP_AMBIENT + (effective_load / max(RATED_LOAD, 1)) * 20 + abs(spd) * 5
        if current_state in ("ACCELERATING", "DECELERATING"):
            target_temp += 5.0

        if "elevator" not in sim.sim_faults:
            target_temp = min(target_temp, safe_temp_max)

        target_temp = clamp(target_temp, ELEVATOR_MOTOR_TEMP_AMBIENT, sim.sensor_limits.get('elev_temperature', (22.0, 90.0))[1])

        if sim.fault_transition_elev == "recovering":
            _ramp_toward_target(sd, "elev_temperature", target_temp, ELEV_RAMP_RATES.get("elev_temperature", 5.0), dt)
            sim._elev_motor_temp = sd["elev_temperature"]
        else:
            if "elevator" not in sim.sim_faults and sim._elev_motor_temp > safe_temp_max:
                sim._elev_motor_temp = max(safe_temp_max, sim._elev_motor_temp - ELEV_RAMP_RATES.get("elev_temperature", 5.0) * dt)
            else:
                temp_diff = target_temp - sim._elev_motor_temp
                sim._elev_motor_temp += temp_diff * 0.05 * dt + random.uniform(-0.2, 0.2) * dt
            sim._elev_motor_temp = clamp(sim._elev_motor_temp, ELEVATOR_MOTOR_TEMP_AMBIENT, sim.sensor_limits.get('elev_temperature', (22.0, 90.0))[1])
            sd["elev_temperature"] = round(sim._elev_motor_temp, 1)
    else:
        target_temp = ELEVATOR_MOTOR_TEMP_AMBIENT
        if sim.fault_transition_elev == "recovering":
            _ramp_toward_target(sd, "elev_temperature", target_temp, ELEV_RAMP_RATES.get("elev_temperature", 5.0), dt)
            sim._elev_motor_temp = sd["elev_temperature"]
        else:
            sim._elev_motor_temp += (ELEVATOR_MOTOR_TEMP_AMBIENT - sim._elev_motor_temp) * 0.05 * dt
            sd["elev_temperature"] = round(clamp(sim._elev_motor_temp, ELEVATOR_MOTOR_TEMP_AMBIENT, sim.sensor_limits.get('elev_temperature', (22.0, 90.0))[1]), 1)

    # ── Elevator voltage simulation ────────────────────────────────────────
    if not sim._elev_power_available:
        sim._elev_voltage = 0.0
    else:
        sim._elev_voltage = 380.0 + random.uniform(-5.0, 5.0)
        if current_state == "ACCELERATING":
            sim._elev_voltage -= 12.0
        if getattr(sim, "_elev_traction_loss", False):
            sim._elev_voltage -= 8.0

    target_volt = clamp(sim._elev_voltage, sim.sensor_limits.get('elev_voltage', (0.0, 500.0))[0], sim.sensor_limits.get('elev_voltage', (0.0, 500.0))[1])
    if sim.fault_transition_elev == "recovering":
        _ramp_toward_target(sd, "elev_voltage", target_volt, ELEV_RAMP_RATES.get("elev_voltage", 30.0), dt)
        sim._elev_voltage = sd["elev_voltage"]
    else:
        current_volt = sd.get("elev_voltage", 380)
        max_volt_ramp = ELEV_RAMP_RATES.get("elev_voltage", 30.0) * dt
        if target_volt > current_volt + max_volt_ramp:
            volt = current_volt + max_volt_ramp
        elif target_volt < current_volt - max_volt_ramp:
            volt = current_volt - max_volt_ramp
        else:
            volt = target_volt
        sd["elev_voltage"] = round(volt, 1)
        sim._elev_voltage = volt

    # ── Elevator vibration simulation ──────────────────────────────────────
    vib_high = thresh.get("elev_vibration", {}).get("high", 3.0)
    safe_vib_max = vib_high * 0.95

    if not sim._elev_power_available and spd == 0:
        target_vib = 0.0
    else:
        base_vib = 0.5 if current_state == "IDLE" else 1.0 + abs(spd) * 0.8
        target_vib = base_vib + random.uniform(0.0, 0.4)
        if getattr(sim, "_elev_traction_loss", False):
            target_vib += 8.5 + random.uniform(0.0, 2.0)

        # Enforce safe normal regime if no fault
        if "elevator" not in sim.sim_faults:
            target_vib = min(target_vib, safe_vib_max)

    target_vib = clamp(target_vib, sim.sensor_limits.get('elev_vibration', (0.0, 10.0))[0], sim.sensor_limits.get('elev_vibration', (0.0, 10.0))[1])
    if sim.fault_transition_elev == "recovering":
        _ramp_toward_target(sd, "elev_vibration", target_vib, ELEV_RAMP_RATES.get("elev_vibration", 2.0), dt)
        sim._elev_vibration = sd["elev_vibration"]
    else:
        current_vib = sd.get("elev_vibration", 0)
        max_vib_ramp = ELEV_RAMP_RATES.get("elev_vibration", 2.0) * dt
        if target_vib > current_vib + max_vib_ramp:
            vib = current_vib + max_vib_ramp
        elif target_vib < current_vib - max_vib_ramp:
            vib = current_vib - max_vib_ramp
        else:
            vib = target_vib
        sd["elev_vibration"] = round(vib, 1)
        sim._elev_vibration = vib

    # ── Elevator motor current simulation ──────────────────────────────────
    if not sim._elev_power_available:
        sim._elev_current = 0.0
    elif current_state == "IDLE":
        sim._elev_current = ELEVATOR_MOTOR_RATED_CURRENT * 0.08 + random.uniform(-0.3, 0.3) * dt
    elif current_state in ("DOOR_OPENING", "DOOR_CLOSING"):
        sim._elev_current = ELEVATOR_MOTOR_RATED_CURRENT * 0.12 + random.uniform(-0.2, 0.2) * dt
    elif current_state == "DOORS_OPEN":
        sim._elev_current = ELEVATOR_MOTOR_RATED_CURRENT * 0.08 + random.uniform(-0.2, 0.2) * dt
    elif abs(spd) > 0.01:
        total_cabin_mass = CABIN_EMPTY_MASS + effective_load
        unbalance = (total_cabin_mass - COUNTERWEIGHT_MASS) * G
        direction = sim._elev_direction

        motor_force_gravity = unbalance * direction

        total_mass = total_cabin_mass + COUNTERWEIGHT_MASS
        inertial_force = total_mass * sim._elev_current_accel

        motor_force = motor_force_gravity + inertial_force
        mechanical_power = motor_force * abs(spd)

        electrical_power = mechanical_power / MOTOR_EFFICIENCY / 1000 if mechanical_power > 0 else mechanical_power * MOTOR_EFFICIENCY / 1000

        load_ratio = effective_load / max(RATED_LOAD, 1)
        base_current = ELEVATOR_MOTOR_RATED_CURRENT * (0.3 + load_ratio * 0.7)

        sim._elev_current = base_current + electrical_power * 2

        if current_state == "ACCELERATING" and sim._elev_timer < 0.5:
            inrush_multiplier = 1.0 + 1.5 * (1.0 - sim._elev_timer / 0.5)
            sim._elev_current *= inrush_multiplier

        sim._elev_current += random.uniform(-0.5, 0.5) * dt

        sim._elev_current = max(sim._elev_current, ELEVATOR_MOTOR_RATED_CURRENT * 0.15)
    else:
        sim._elev_current = ELEVATOR_MOTOR_RATED_CURRENT * 0.15 + random.uniform(-0.3, 0.3) * dt

    target_curr = clamp(sim._elev_current, sim.sensor_limits.get('elev_current', (0.0, 40.0))[0], sim.sensor_limits.get('elev_current', (0.0, 40.0))[1])
    if "elevator" not in sim.sim_faults:
        current_high = thresh.get("elev_current", {}).get("high", 25.0)
        safe_current_max = current_high * 0.95
        target_curr = min(target_curr, safe_current_max)

    if sim.fault_transition_elev == "recovering":
        _ramp_toward_target(sd, "elev_current", target_curr, ELEV_RAMP_RATES.get("elev_current", 4.0), dt)
        sim._elev_current = sd["elev_current"]
    else:
        sd["elev_current"] = round(target_curr, 1)
        sim._elev_current = target_curr

    sd["elevator_state"] = current_state
