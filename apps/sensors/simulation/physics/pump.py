import random

from apps.sensors.sensor_config import PUMP_VARS
from apps.sensors.simulation.constants import (
    PUMP_P0, PUMP_K, T_AMBIENT,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.utils import clamp


# Tank physics constants
# _TANK_BUILDING_DEMAND is now dynamically calculated to balance inflow

# ── Tasas de ramping progresivo por variable (unidades por tick) ──
PUMP_RAMP_RATES = {
    "pump_flow_rate":     3.0,   # l/s/tick  — 12→0 en ~4s
    "pump_pressure":      1.5,   # bar/tick  — 5→0 en ~3s
    "pump_temperature":   8.0,   # °C/tick   — 50→90 en ~5s (masa térmica)
    "pump_vibration":     2.0,   # mm/s/tick — 1→10 en ~4.5s
    "pump_current":       4.0,   # A/tick    — 13→0/25 en ~3-6s
    "pump_voltage":       30.0,  # V/tick    — 220→0/300 en ~7-10s
    "pump_tank_level":    5.0,   # %/tick    — 50→0 en ~10s
    "pump_water_quality": 30.0,  # ppm/tick  — 200→600 en ~13s
}


def _rand_walk(current: float, step: float, lo: float, hi: float) -> float:
    return clamp(current + random.uniform(-step, step), lo, hi)


def _update_pump(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed

    # â”€â”€ Tank level physics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if sim.pump_on:
        is_pumping = "pump" not in sim.sim_faults
        inflow = sd.get("pump_flow_rate", 0.0) if is_pumping else 0.0

        is_dry_run = sim.sim_faults.get("pump") == "dry_run"
        if not is_dry_run:
            from apps.thresholds.services import get_thresholds
            thresh = get_thresholds(sim.edificio_id)
            flow_high = thresh.get("pump_flow_rate", {}).get("high", 18.0)
            target_max = max(5.0, flow_high * 0.85)
            target_min = max(0.0, target_max - 5.0)
            outflow = (target_max + target_min) / 2.0 + random.uniform(-1.0, 1.0)
        else:
            outflow = 0.0

        net = inflow - outflow
        d_tank = net * 0.05 * dt + random.uniform(-0.1, 0.1) * dt
        
        new_tank = sd["pump_tank_level"] + d_tank
        
        # Enforce safe normal regime for tank level if no fault
        if "pump" not in sim.sim_faults:
            tank_t = thresh.get("pump_tank_level", {})
            safe_tank_min = tank_t.get("high", 20.0) + (tank_t.get("critic", 90.0) - tank_t.get("high", 20.0)) * 0.25
            safe_tank_max = tank_t.get("critic", 90.0) - (tank_t.get("critic", 90.0) - tank_t.get("high", 20.0)) * 0.25
            if new_tank < safe_tank_min:
                new_tank = min(safe_tank_min, new_tank + 5.0 * dt)
            elif new_tank > safe_tank_max:
                new_tank = max(safe_tank_max, new_tank - 5.0 * dt)
            
        sd["pump_tank_level"] = round(clamp(new_tank, sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[0], sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[1]), 1)

    # Float switch automático eliminado — la bomba se controla únicamente de forma manual.

    # â”€â”€ Dispatch to correct operating mode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Recovery countdown (debe ejecutarse incluso con bomba apagada,
    # de lo contrario auto-proteccion deja fault_transition atascado en "recovering")
    if sim.fault_transition_pump == "recovering":
        sim._fault_transition_ticks_pump -= 1
        if sim._fault_transition_ticks_pump <= 0:
            sim.fault_transition_pump = "stable"

    if not sim.pump_on:
        _set_pump_idle(sim, sd, dt)
        return
    if "pump" in sim.sim_faults:
        _apply_pump_fault(sim, sd, dt)
        return
    if sim._pump_start_grace_ticks > 0:
        sim._pump_start_grace_ticks -= 1
    _run_pump_normal(sim, sd, dt)


def _set_pump_idle(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    _ramp_toward_target(sd, "pump_flow_rate", 0.0, PUMP_RAMP_RATES.get("pump_flow_rate", 3.0), dt)
    _ramp_toward_target(sd, "pump_pressure", 1.0, PUMP_RAMP_RATES.get("pump_pressure", 1.5), dt)
    _ramp_toward_target(sd, "pump_vibration", 0.0, PUMP_RAMP_RATES.get("pump_vibration", 2.0), dt)
    _ramp_toward_target(sd, "pump_current", 0.0, PUMP_RAMP_RATES.get("pump_current", 4.0), dt)
    sd["pump_temperature"] = round(
        clamp(sd["pump_temperature"] + (T_AMBIENT - sd["pump_temperature"]) * 0.05 * dt,
               T_AMBIENT, sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[1]), 1
    )
    volt = sd["pump_voltage"]
    volt_diff = 220.0 - volt
    sd["pump_voltage"] = round(
        clamp(
            volt + volt_diff * 0.05 * dt,
            0.0, sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[1],
        ), 1
    )
    # Reducimos la fluctuación a medida que el caudal llega a cero
    current_flow = sd.get("pump_flow_rate", 0.0)
    noise_amp = max(0.0, min(1.0, current_flow / 5.0))
    
    qual = sd.get("pump_water_quality", 200.0)
    if noise_amp > 0.0:
        qual += random.uniform(-noise_amp, noise_amp) * dt
        
    sd["pump_water_quality"] = round(
        clamp(qual, sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[0], sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[1]), 1
    )


def _ramp_toward_target(sd: dict, k: str, target: float, rate: float, dt: float) -> bool:
    current = sd[k]
    diff = abs(target - current)
    if diff < 0.3:
        sd[k] = target
        return True
    step = rate * dt
    if diff <= step:
        sd[k] = target
        return True
    sd[k] = current + step if target > current else current - step
    return False


def _apply_pump_fault(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    fault_type = sim.sim_faults.get("pump")

    temp_sd = sd.copy()

    _PUMP_FAULT_HANDLERS = {
        "dry_run":          _apply_dry_run,
        "blocked_discharge": _apply_blocked_discharge,
        "pipe_burst":        _apply_pipe_burst,
        "cavitation":        _apply_cavitation,
        "overheat":          _apply_overheat,
        "power_surge":       _apply_power_surge,
        "power_outage":      _apply_power_outage,
        "bearing_failure":   _apply_bearing_failure,
    }
    handler = _PUMP_FAULT_HANDLERS.get(fault_type)
    if handler:
        handler(sim, temp_sd, dt)

    all_reached = True
    for k in PUMP_VARS:
        target = temp_sd[k]
        bounds = sim.sensor_limits.get(k)
        if bounds:
            target = max(bounds[0], min(bounds[1], target))

        rate = PUMP_RAMP_RATES.get(k, 2.0)
        if not _ramp_toward_target(sd, k, target, rate, dt):
            all_reached = False

    if fault_type != "power_outage":
        _clamp_pump_values(sim, sd)

    sim.fault_transition_pump = "stable" if all_reached else "injecting"


def _apply_dry_run(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = 0.0
    sd["pump_pressure"]    = 0.0
    sd["pump_temperature"] = 90.0
    sd["pump_vibration"]   = 10.0
    sd["pump_current"]     = 0.0
    sd["pump_tank_level"]  = 0.0

def _apply_blocked_discharge(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = 0.0
    sd["pump_pressure"]    = 10.0
    sd["pump_vibration"]   = 10.0
    sd["pump_temperature"] = 90.0
    sd["pump_current"]     = 25.0
    sd["pump_tank_level"]  = clamp(sd["pump_tank_level"] + 0.1 * dt, 0.0, 100.0)

def _apply_pipe_burst(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = 50.0
    sd["pump_pressure"]    = 0.0
    sd["pump_vibration"]   = 10.0
    sd["pump_current"]     = 25.0
    sd["pump_temperature"] = 90.0
    sd["pump_tank_level"]  = 0.0

def _apply_cavitation(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = random.uniform(25.0, 35.0)
    sd["pump_vibration"]   = 10.0
    sd["pump_pressure"]    = random.uniform(0.0, 0.5)
    sd["pump_temperature"] = 90.0
    sd["pump_current"]     = random.uniform(25.0, 30.0)

def _apply_overheat(sim, sd: dict, dt: float) -> None:
    sd["pump_temperature"] = 100.0
    sd["pump_vibration"]   = 10.0
    sd["pump_current"]     = 25.0
    sd["pump_flow_rate"]   = 0.0

def _apply_power_surge(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = 0.0
    sd["pump_pressure"]    = 0.0
    sd["pump_voltage"]     = 300.0
    sd["pump_current"]     = 30.0
    sd["pump_temperature"] = 90.0
    sd["pump_vibration"]   = 10.0

def _apply_power_outage(sim, sd: dict, dt: float) -> None:
    sd["pump_voltage"]     = 0.0
    sd["pump_current"]     = 0.0
    sd["pump_flow_rate"]   = 0.0
    sd["pump_pressure"]    = 0.0
    sd["pump_vibration"]   = 0.0
    sd["pump_temperature"] = T_AMBIENT

def _apply_bearing_failure(sim, sd: dict, dt: float) -> None:
    sd["pump_vibration"]     = 10.0
    sd["pump_temperature"]   = 90.0
    sd["pump_current"]       = 25.0
    sd["pump_water_quality"] = 600.0
    sd["pump_flow_rate"]     = 0.0
    sd["pump_pressure"]      = 0.0

def _clamp_pump_values(sim, sd: dict) -> None:
    sd["pump_flow_rate"]   = round(clamp(sd["pump_flow_rate"],   sim.sensor_limits.get('pump_flow_rate', (0.0, 50000.0))[0],       sim.sensor_limits.get('pump_flow_rate', (0.0, 50000.0))[1]),       1)
    sd["pump_pressure"]    = round(clamp(sd["pump_pressure"],    sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0],       sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[1]),       1)
    sd["pump_temperature"] = round(clamp(sd["pump_temperature"], sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[0],       sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[1]),       1)
    sd["pump_vibration"]   = round(clamp(sd["pump_vibration"],   sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],        sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1]),        1)
    sd["pump_voltage"]     = round(clamp(sd["pump_voltage"],     sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[0],       sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[1]),       1)
    sd["pump_current"]     = round(clamp(sd["pump_current"],     sim.sensor_limits.get('pump_current', (0.0, 30.0))[0],       sim.sensor_limits.get('pump_current', (0.0, 30.0))[1]),       1)
    sd["pump_water_quality"] = round(clamp(sd.get("pump_water_quality", 200.0), sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[0], sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[1]), 1)


def _run_pump_normal(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    from apps.thresholds.services import get_thresholds
    thresh = get_thresholds(sim.edificio_id)
    
    # â”€â”€ Voltage â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    volt = sd["pump_voltage"] + (220.0 - sd["pump_voltage"]) * 0.05 * dt + random.uniform(-0.5, 0.5) * dt
    sd["pump_voltage"] = round(clamp(volt, sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[0], sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[1]), 1)

    volt = sd["pump_voltage"]

    # Voltage collapse â†’ all outputs drop
    if volt < 50.0:
        sd["pump_flow_rate"]  = round(clamp(sd["pump_flow_rate"]  - 5.0 * dt, 0.0, sim.sensor_limits.get('pump_flow_rate', (0.0, 50000.0))[1]), 1)
        sd["pump_pressure"]   = round(clamp(sd["pump_pressure"]   - 2.0 * dt, 0.0, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[1]), 1)
        sd["pump_vibration"]  = round(clamp(sd["pump_vibration"]  - 2.0 * dt, 0.0, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1]),  1)
        sd["pump_current"]    = round(clamp(sd["pump_current"]    - 5.0 * dt, 0.0, sim.sensor_limits.get('pump_current', (0.0, 30.0))[1]),  1)
        sd["pump_temperature"] = round(
            clamp(sd["pump_temperature"] + (T_AMBIENT - sd["pump_temperature"]) * 0.05 * dt,
                   sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[1]), 1
        )
        return

    # â”€â”€ Tank < 10% â†’ cavitation / starvation mode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    tank = sd["pump_tank_level"]
    if tank < 10.0:
        sd["pump_flow_rate"]   = round(clamp(sd["pump_flow_rate"]   - 3.0 * dt, sim.sensor_limits.get('pump_flow_rate', (0.0, 50000.0))[0], 2.0),        1)
        sd["pump_pressure"]    = round(clamp(sd["pump_pressure"]    - 0.8 * dt, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0], 1.0),        1)
        sd["pump_vibration"]   = round(clamp(sd["pump_vibration"]   + 1.2 * dt, 0.5, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1]),        1)
        sd["pump_temperature"] = round(clamp(sd["pump_temperature"] + 2.0 * dt, sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[1]), 1)
        sd["pump_current"]     = round(clamp(sd["pump_current"]     - 2.0 * dt, 0.0, 8.0),   1)
        return

    # â”€â”€ Normal operating regime â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    flow_high = thresh.get("pump_flow_rate", {}).get("high", 18.0)
    target_max = max(5.0, flow_high * 0.85)
    target_min = max(0.0, target_max - 5.0)
    sim._pump_demand = _rand_walk(sim._pump_demand, 0.5 * dt, target_min, target_max)
    flow = sim._pump_demand
    current_flow = sd.get("pump_flow_rate", 0)
    max_flow_ramp = 3.0 * dt
    if flow > current_flow + max_flow_ramp:
        flow = current_flow + max_flow_ramp
    elif flow < current_flow - max_flow_ramp:
        flow = current_flow - max_flow_ramp

    target_pressure = max(0.5, PUMP_P0 - PUMP_K * flow ** 2) + random.uniform(-0.1, 0.1) * dt
    if "pump" not in sim.sim_faults:
        press_t = thresh.get("pump_pressure", {})
        safe_press_min = press_t.get("high", 1.0) + (press_t.get("critic", 6.0) - press_t.get("high", 1.0)) * 0.25
        safe_press_max = press_t.get("critic", 6.0) - (press_t.get("critic", 6.0) - press_t.get("high", 1.0)) * 0.25
        target_pressure = max(safe_press_min, min(target_pressure, safe_press_max))

    current_press = sd.get("pump_pressure", 0)
    max_press_ramp = 1.5 * dt
    if target_pressure > current_press + max_press_ramp:
        pressure = current_press + max_press_ramp
    elif target_pressure < current_press - max_press_ramp:
        pressure = current_press - max_press_ramp
    else:
        pressure = target_pressure

    # First-order thermal model
    target_temp = 50.0 + (flow * pressure * 0.1)
    if "pump" not in sim.sim_faults:
        temp_t = thresh.get("pump_temperature", {})
        safe_temp_max = temp_t.get("high", 60.0) * 0.95
        target_temp = min(target_temp, safe_temp_max)

    temp_diff   = target_temp - sd["pump_temperature"]
    temp = sd["pump_temperature"] + temp_diff * 0.05 * dt + random.uniform(-0.1, 0.1) * dt

    target_vib  = 0.5 + flow / 25.0 + max(0.0, temp - 65.0) / 40.0 + random.uniform(-0.2, 0.3) * dt
    if "pump" not in sim.sim_faults:
        vib_t = thresh.get("pump_vibration", {})
        safe_vib_max = vib_t.get("high", 4.5) * 0.95
        target_vib = min(target_vib, safe_vib_max)

    current_vib = sd.get("pump_vibration", 0)
    max_vib_ramp = 2.0 * dt
    if target_vib > current_vib + max_vib_ramp:
        vib = current_vib + max_vib_ramp
    elif target_vib < current_vib - max_vib_ramp:
        vib = current_vib - max_vib_ramp
    else:
        vib = target_vib

    # El trabajo mecánico incluye el caudal y una resistencia parasita por presión (Shutoff head)
    # Modelo eléctrico ajustado: nominal ~13 A @ 13 l/s, 5 bar, 220 V
    target_curr = (flow * pressure * 28.0 + pressure * 120.0) / (volt * 0.85) + random.uniform(-0.5, 0.5) * dt
    if "pump" not in sim.sim_faults:
        curr_t = thresh.get("pump_current", {})
        safe_curr_max = curr_t.get("high", 16.0) * 0.95
        target_curr = min(target_curr, safe_curr_max)

    current_curr = sd.get("pump_current", 0)
    max_curr_ramp = 4.0 * dt
    if target_curr > current_curr + max_curr_ramp:
        curr = current_curr + max_curr_ramp
    elif target_curr < current_curr - max_curr_ramp:
        curr = current_curr - max_curr_ramp
    else:
        curr = target_curr

    sd["pump_flow_rate"]   = round(clamp(flow,     sim.sensor_limits.get('pump_flow_rate', (0.0, 50000.0))[0],       sim.sensor_limits.get('pump_flow_rate', (0.0, 50000.0))[1]),       1)
    sd["pump_pressure"]    = round(clamp(pressure, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0],       sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[1]),       1)
    sd["pump_temperature"] = round(clamp(temp,     sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[0],       sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[1]),       1)
    sd["pump_vibration"]   = round(clamp(vib,      sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],        sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1]),        1)
    sd["pump_current"]     = round(clamp(curr,     sim.sensor_limits.get('pump_current', (0.0, 30.0))[0],       sim.sensor_limits.get('pump_current', (0.0, 30.0))[1]),       1)
    qual = sd.get("pump_water_quality", 200.0)
    qual += (200.0 - qual) * 0.05 * dt + random.uniform(-2.0, 2.0) * dt
    sd["pump_water_quality"] = round(clamp(qual, sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[0], sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[1]), 1)

