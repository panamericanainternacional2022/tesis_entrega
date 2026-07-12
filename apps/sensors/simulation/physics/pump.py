import random

from apps.sensors.sensor_config import SENSOR_RANGES, PUMP_VARS
from apps.sensors.simulation.constants import (
    PUMP_P0, PUMP_K, T_AMBIENT,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.utils import clamp, is_locked

_FLOW_LOW, _FLOW_HIGH = SENSOR_RANGES["pump_flow_rate"]
_PRES_LOW, _PRES_HIGH = SENSOR_RANGES["pump_pressure"]
_TEMP_LOW, _TEMP_HIGH = SENSOR_RANGES["pump_temperature"]
_VIB_LOW, _VIB_HIGH = SENSOR_RANGES["pump_vibration"]
_TANK_LOW, _TANK_HIGH = SENSOR_RANGES["pump_tank_level"]
_VOLT_LOW, _VOLT_HIGH = SENSOR_RANGES["pump_voltage"]
_CURR_LOW, _CURR_HIGH = SENSOR_RANGES["pump_current"]
_QUAL_LOW, _QUAL_HIGH = SENSOR_RANGES["pump_water_quality"]

# Tank physics constants
_TANK_BUILDING_DEMAND = 12.0    # l/s constant building water consumption
_TANK_FULL_THRESHOLD = 85.0     # % — float switch turns pump OFF when tank >= this
_TANK_LOW_THRESHOLD = 80.0      # % — float switch turns pump ON when tank < this


def _rand_walk(current: float, step: float, lo: float, hi: float) -> float:
    return clamp(current + random.uniform(-step, step), lo, hi)


def _update_pump(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed

    # ── Tank level physics ──────────────────────────────────────────────────
    if not is_locked(sim, "pump_tank_level") and sim.pump_on:
        is_pumping = "pump" not in sim.sim_faults
        inflow = sd.get("pump_flow_rate", 0.0) if is_pumping else 0.0

        is_dry_run = sim.sim_faults.get("pump") == "dry_run"
        if not is_dry_run:
            outflow = _TANK_BUILDING_DEMAND + random.uniform(-1.0, 1.0)
        else:
            outflow = 0.0

        net = inflow - outflow
        d_tank = net * 0.05 * dt + random.uniform(-0.1, 0.1) * dt
        sd["pump_tank_level"] = round(clamp(sd["pump_tank_level"] + d_tank, 0.0, 100.0), 1)

    # ── Float switch: auto turn pump ON/OFF based on tank level ────────────
    if not getattr(sim, "manual_pump_override", False):
        tank = sd["pump_tank_level"]
        if tank >= _TANK_FULL_THRESHOLD and sim.pump_on:
            sim.pump_on = False
        elif tank < _TANK_LOW_THRESHOLD and not sim.pump_on:
            sim.pump_on = True

    # ── Dispatch to correct operating mode ─────────────────────────────────
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
    if not is_locked(sim, "pump_flow_rate"):
        sd["pump_flow_rate"] = 0.0
    if not is_locked(sim, "pump_pressure"):
        sd["pump_pressure"] = 0.0
    if not is_locked(sim, "pump_vibration"):
        sd["pump_vibration"] = 0.0
    if not is_locked(sim, "pump_current"):
        sd["pump_current"] = 0.0
    if not is_locked(sim, "pump_temperature"):
        sd["pump_temperature"] = round(
            clamp(sd["pump_temperature"] - 0.5 * dt, _TEMP_LOW, _TEMP_HIGH), 1
        )
    if not is_locked(sim, "pump_voltage"):
        volt = sd["pump_voltage"]
        volt_diff = 220.0 - volt
        sd["pump_voltage"] = round(
            clamp(
                volt + volt_diff * 0.05 * dt + random.uniform(-0.5, 0.5) * dt,
                _VOLT_LOW, _VOLT_HIGH,
            ), 1
        )
    if not is_locked(sim, "pump_water_quality"):
        sd["pump_water_quality"] = round(
            clamp(sd.get("pump_water_quality", 200.0) + random.uniform(-1.0, 1.0) * dt, _QUAL_LOW, _QUAL_HIGH), 1
        )


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
        handler(temp_sd, dt)

    for k in PUMP_VARS:
        sd[k] = temp_sd[k]

    if fault_type != "power_outage":
        _clamp_pump_values(sd)


def _apply_dry_run(sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]  = clamp(sd["pump_flow_rate"]  - 5.0 * dt, 0, 0.5)
    sd["pump_pressure"]   = clamp(sd["pump_pressure"]   - 2.0 * dt, 0, 0.5)
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 1.5 * dt, 0, 130)
    sd["pump_vibration"]  = clamp(sd["pump_vibration"]  + 0.5 * dt, 0, 15)
    sd["pump_current"]    = clamp(sd["pump_current"]    - 2.0 * dt, 1.0, 70)
    sd["pump_tank_level"] = clamp(sd["pump_tank_level"] - 15.0 * dt, 0, 10)


def _apply_blocked_discharge(sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = clamp(sd["pump_flow_rate"]   - 5.0 * dt, 0, 0.5)
    sd["pump_pressure"]    = clamp(sd["pump_pressure"]    + 1.5 * dt, 0, 12)
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + 0.8 * dt, 0, 15)
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 3.0 * dt, 0, 130)
    sd["pump_current"]     = clamp(sd["pump_current"]     + 2.0 * dt, 10.0, 70)
    sd["pump_tank_level"]  = clamp(sd["pump_tank_level"]  + 0.1 * dt, 0, 100)


def _apply_pipe_burst(sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]  = clamp(sd["pump_flow_rate"]  + 3.0 * dt, 0, 60)
    sd["pump_pressure"]   = clamp(sd["pump_pressure"]   - 0.8 * dt, 0, 2)
    sd["pump_vibration"]  = clamp(sd["pump_vibration"]  + 0.6 * dt, 0, 15)
    sd["pump_current"]    = clamp(sd["pump_current"]    + 8.0 * dt, 0, 70)
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 1.0 * dt, 0, 130)
    sd["pump_tank_level"] = clamp(sd["pump_tank_level"] - 5.0 * dt, 0, 100)


def _apply_cavitation(sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]  = clamp(sd["pump_flow_rate"]  + random.uniform(-5, 5) * dt, 0, 60)
    sd["pump_vibration"]  = clamp(sd["pump_vibration"]  + random.uniform(0.5, 2.0) * dt, 0, 15)
    sd["pump_pressure"]   = clamp(sd["pump_pressure"]   + random.uniform(-0.5, 0.5) * dt, 0, 12)
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 1.2 * dt, 0, 130)


def _apply_overheat(sd: dict, dt: float) -> None:
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 2.0 * dt, 0, 130)
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + 0.3 * dt, 0, 15)


def _apply_power_surge(sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = clamp(sd["pump_flow_rate"]   - 10.0 * dt, 0, 0.5)
    sd["pump_pressure"]    = clamp(sd["pump_pressure"]    - 5.0 * dt, 0, 0.5)
    sd["pump_voltage"]     = clamp(sd["pump_voltage"]     - 15.0 * dt, 180, 260)
    sd["pump_current"]     = clamp(sd["pump_current"]     + 12.0 * dt, 0, 70)
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 3.0 * dt, 0, 130)
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + 1.5 * dt, 0, 15)


def _apply_power_outage(sd: dict, dt: float) -> None:
    sd["pump_voltage"]     = 0.0
    sd["pump_current"]     = 0.0
    sd["pump_flow_rate"]   = clamp(sd["pump_flow_rate"]   - 20.0 * dt, 0, 60)
    sd["pump_pressure"]    = clamp(sd["pump_pressure"]    - 4.0 * dt, 0, 12)
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   - 5.0 * dt, 0, 15)
    sd["pump_temperature"] = clamp(sd["pump_temperature"] - 0.5 * dt, T_AMBIENT, _TEMP_HIGH)

def _apply_bearing_failure(sd: dict, dt: float) -> None:
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + 1.5 * dt, 0, 15)
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 3.0 * dt, 0, 130)
    sd["pump_current"]     = clamp(sd["pump_current"]     + 4.0 * dt, 10.0, 70)
    sd["pump_water_quality"] = clamp(sd.get("pump_water_quality", 200.0) + 15.0 * dt, 0, 1000)

def _clamp_pump_values(sd: dict) -> None:
    sd["pump_flow_rate"]   = round(clamp(sd["pump_flow_rate"],   _FLOW_LOW,       _FLOW_HIGH),       1)
    sd["pump_pressure"]    = round(clamp(sd["pump_pressure"],    _PRES_LOW,       _PRES_HIGH),       1)
    sd["pump_temperature"] = round(clamp(sd["pump_temperature"], _TEMP_LOW,       _TEMP_HIGH),       1)
    sd["pump_vibration"]   = round(clamp(sd["pump_vibration"],   _VIB_LOW,        _VIB_HIGH),        1)
    sd["pump_voltage"]     = round(clamp(sd["pump_voltage"],     _VOLT_LOW,       _VOLT_HIGH),       1)
    sd["pump_current"]     = round(clamp(sd["pump_current"],     _CURR_LOW,       _CURR_HIGH),       1)
    sd["pump_water_quality"] = round(clamp(sd.get("pump_water_quality", 200.0), _QUAL_LOW, _QUAL_HIGH), 1)


def _run_pump_normal(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    # ── Voltage ────────────────────────────────────────────────────────────
    if not is_locked(sim, "pump_voltage"):
        volt = sd["pump_voltage"] + (220.0 - sd["pump_voltage"]) * 0.05 * dt + random.uniform(-0.5, 0.5) * dt
        sd["pump_voltage"] = round(clamp(volt, _VOLT_LOW, _VOLT_HIGH), 1)

    volt = sd["pump_voltage"]

    # Voltage collapse → all outputs drop
    if volt < 50.0:
        if not is_locked(sim, "pump_flow_rate"):
            sd["pump_flow_rate"]  = round(clamp(sd["pump_flow_rate"]  - 5.0 * dt, 0.0, _FLOW_HIGH), 1)
        if not is_locked(sim, "pump_pressure"):
            sd["pump_pressure"]   = round(clamp(sd["pump_pressure"]   - 2.0 * dt, 0.0, _PRES_HIGH), 1)
        if not is_locked(sim, "pump_vibration"):
            sd["pump_vibration"]  = round(clamp(sd["pump_vibration"]  - 2.0 * dt, 0.0, _VIB_HIGH),  1)
        if not is_locked(sim, "pump_current"):
            sd["pump_current"]    = round(clamp(sd["pump_current"]    - 5.0 * dt, 0.0, _CURR_HIGH),  1)
        if not is_locked(sim, "pump_temperature"):
            sd["pump_temperature"] = round(
                clamp(sd["pump_temperature"] + (T_AMBIENT - sd["pump_temperature"]) * 0.02 * dt,
                       _TEMP_LOW, _TEMP_HIGH), 1
            )
        return

    # ── Tank < 10% → cavitation / starvation mode ──────────────────────────
    tank = sd["pump_tank_level"]
    if tank < 10.0:
        if not is_locked(sim, "pump_flow_rate"):
            sd["pump_flow_rate"]   = round(clamp(sd["pump_flow_rate"]   - 3.0 * dt, 0.0, 2.0),   1)
        if not is_locked(sim, "pump_pressure"):
            sd["pump_pressure"]    = round(clamp(sd["pump_pressure"]    - 0.8 * dt, 0.0, 1.0),   1)
        if not is_locked(sim, "pump_vibration"):
            sd["pump_vibration"]   = round(clamp(sd["pump_vibration"]   + 1.2 * dt, 0.5, 15.0),  1)
        if not is_locked(sim, "pump_temperature"):
            sd["pump_temperature"] = round(clamp(sd["pump_temperature"] + 2.0 * dt, _TEMP_LOW, 120.0), 1)
        if not is_locked(sim, "pump_current"):
            sd["pump_current"]     = round(clamp(sd["pump_current"]     - 2.0 * dt, 0.0, 8.0),   1)
        return

    # ── Normal operating regime ────────────────────────────────────────────
    _DEMAND_MAX = 16.0
    if is_locked(sim, "pump_flow_rate"):
        flow = sd["pump_flow_rate"]
        sim._pump_demand = clamp(flow, 8.0, _DEMAND_MAX)
    else:
        sim._pump_demand = _rand_walk(sim._pump_demand, 0.5 * dt, 10.0, _DEMAND_MAX)
        flow = sim._pump_demand
        current_flow = sd.get("pump_flow_rate", 0)
        max_flow_ramp = 3.0 * dt
        if flow > current_flow + max_flow_ramp:
            flow = current_flow + max_flow_ramp
        elif flow < current_flow - max_flow_ramp:
            flow = current_flow - max_flow_ramp

    pressure = max(0.5, PUMP_P0 - PUMP_K * flow ** 2) + random.uniform(-0.1, 0.1) * dt
    current_press = sd.get("pump_pressure", 0)
    max_press_ramp = 1.5 * dt
    if pressure > current_press + max_press_ramp:
        pressure = current_press + max_press_ramp
    elif pressure < current_press - max_press_ramp:
        pressure = current_press - max_press_ramp

    # First-order thermal model
    target_temp = 50.0 + (flow * pressure * 0.1)
    temp_diff   = target_temp - sd["pump_temperature"]
    temp = sd["pump_temperature"] + temp_diff * 0.02 * dt + random.uniform(-0.1, 0.1) * dt

    vib  = 0.5 + flow / 25.0 + max(0.0, temp - 65.0) / 40.0 + random.uniform(-0.2, 0.3) * dt
    # El trabajo mecánico incluye el caudal y una resistencia parasita por presión (Shutoff head)
    curr = (flow * pressure * 40.0 + pressure * 150.0) / (volt * 0.75) + random.uniform(-0.5, 0.5) * dt

    if not is_locked(sim, "pump_flow_rate"):
        sd["pump_flow_rate"]   = round(clamp(flow,     _FLOW_LOW,       _FLOW_HIGH),       1)
    if not is_locked(sim, "pump_pressure"):
        sd["pump_pressure"]    = round(clamp(pressure, _PRES_LOW,       _PRES_HIGH),       1)
    if not is_locked(sim, "pump_temperature"):
        sd["pump_temperature"] = round(clamp(temp,     _TEMP_LOW,       _TEMP_HIGH),       1)
    if not is_locked(sim, "pump_vibration"):
        sd["pump_vibration"]   = round(clamp(vib,      _VIB_LOW,        _VIB_HIGH),        1)
    if not is_locked(sim, "pump_current"):
        sd["pump_current"]     = round(clamp(curr,     _CURR_LOW,       _CURR_HIGH),       1)
    if not is_locked(sim, "pump_water_quality"):
        qual = sd.get("pump_water_quality", 200.0)
        qual += (200.0 - qual) * 0.05 * dt + random.uniform(-2.0, 2.0) * dt
        sd["pump_water_quality"] = round(clamp(qual, _QUAL_LOW, _QUAL_HIGH), 1)
