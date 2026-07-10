import random
import time

from apps.sensors.sensor_config import SENSOR_RANGES, PUMP_VARS
from apps.sensors.simulation.constants import (
    PUMP_P0, PUMP_K, T_AMBIENT,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.utils import clamp, is_locked

_FLOW_LOW, _FLOW_HIGH = SENSOR_RANGES["flow_rate"]
_PRES_LOW, _PRES_HIGH = SENSOR_RANGES["pressure"]
_TEMP_LOW, _TEMP_HIGH = SENSOR_RANGES["temperature"]
_VIB_LOW, _VIB_HIGH = SENSOR_RANGES["vibration"]
_TANK_LOW, _TANK_HIGH = SENSOR_RANGES["tank_level"]
_VOLT_LOW, _VOLT_HIGH = SENSOR_RANGES["voltage"]
_CURR_LOW, _CURR_HIGH = SENSOR_RANGES["current"]
_PUMP_ENERGY_LOW, _PUMP_ENERGY_HIGH = SENSOR_RANGES["pump_energy"]

# Tank physics constants
_TANK_BUILDING_DEMAND = 12.0    # l/s constant building water consumption
_TANK_FULL_THRESHOLD = 85.0     # % — float switch turns pump OFF when tank >= this
_TANK_LOW_THRESHOLD = 80.0      # % — float switch turns pump ON when tank < this


def _rand_walk(current: float, step: float, lo: float, hi: float) -> float:
    return clamp(current + random.uniform(-step, step), lo, hi)


def _compute_pump_energy(flow: float, pressure: float, volt: float) -> float:
    if flow <= 0 or pressure <= 0 or volt < 50:
        return 0.2
    hyd_power = flow * pressure / 10
    elec_power = hyd_power / 0.85 + 0.2
    return elec_power



def _update_pump(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed

    # ── Tank level physics ──────────────────────────────────────────────────
    # The pump fills the tank (inflow).  The building continuously consumes
    # water (outflow), modelled as a constant demand with small fluctuations.
    # When the pump is OFF the tank level freezes (no inflow, no outflow).
    if not is_locked(sim, "tank_level") and sim.pump_on:
        is_pumping = "pump" not in sim.sim_faults
        # Inflow = water from mains pumped into tank
        inflow = sd.get("flow_rate", 0.0) if is_pumping else 0.0

        # Outflow = building consumption (only when pump is on)
        is_dry_run = sim.sim_faults.get("pump") == "dry_run"
        if not is_dry_run:
            outflow = _TANK_BUILDING_DEMAND + random.uniform(-1.0, 1.0)
        else:
            # During dry-run, no water in tank to consume
            outflow = 0.0

        # Δ tank level per second, scaled to % per tick
        net = inflow - outflow
        d_tank = net * 0.05 * dt + random.uniform(-0.1, 0.1) * dt
        sd["tank_level"] = round(clamp(sd["tank_level"] + d_tank, 0.0, 100.0), 1)

    # ── Float switch: auto turn pump ON/OFF based on tank level ────────────
    if not getattr(sim, "manual_pump_override", False):
        tank = sd["tank_level"]
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
    if not is_locked(sim, "flow_rate"):
        sd["flow_rate"] = 0.0
    if not is_locked(sim, "pressure"):
        sd["pressure"] = 0.0
    if not is_locked(sim, "vibration"):
        sd["vibration"] = 0.0
    if not is_locked(sim, "current"):
        sd["current"] = 0.0
    if not is_locked(sim, "pump_energy"):
        sd["pump_energy"] = 0.0
    if not is_locked(sim, "temperature"):
        sd["temperature"] = round(
            clamp(sd["temperature"] - 0.5 * dt, _TEMP_LOW, _TEMP_HIGH), 1
        )
    if not is_locked(sim, "voltage"):
        volt = sd["voltage"]
        volt_diff = 220.0 - volt
        sd["voltage"] = round(
            clamp(
                volt + volt_diff * 0.05 * dt + random.uniform(-0.5, 0.5) * dt,
                _VOLT_LOW, _VOLT_HIGH,
            ), 1
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
    }
    handler = _PUMP_FAULT_HANDLERS.get(fault_type)
    if handler:
        handler(temp_sd, dt)

    temp_sd["pump_energy"] = _compute_pump_energy(
        temp_sd.get("flow_rate", 0),
        temp_sd.get("pressure", 0),
        temp_sd.get("voltage", 220),
    )

    # Special-case energy overrides for faults where hydraulic-only
    # computation does not reflect real motor load.
    if fault_type == "overheat":
        temp_sd["pump_energy"] = clamp(temp_sd["pump_energy"] * 1.5, _PUMP_ENERGY_LOW, _PUMP_ENERGY_HIGH)

    for k in PUMP_VARS:
        sd[k] = temp_sd[k]

    if fault_type != "power_outage":
        _clamp_pump_values(sd)


def _apply_dry_run(sd: dict, dt: float) -> None:
    """Dry run: pump running but tank is empty → cavitates, overheats, no flow.
    Motor spins freely drawing ~1.5A with no hydraulic load."""
    sd["flow_rate"]  = clamp(sd["flow_rate"]  - 5.0 * dt, 0, 0.5)
    sd["pressure"]   = clamp(sd["pressure"]   - 2.0 * dt, 0, 0.5)
    sd["temperature"] = clamp(sd["temperature"] + 1.5 * dt, 0, 130)
    sd["vibration"]  = clamp(sd["vibration"]  + 0.5 * dt, 0, 15)
    sd["current"]    = clamp(sd["current"]    - 2.0 * dt, 1.0, 70)
    sd["tank_level"] = clamp(sd["tank_level"] - 15.0 * dt, 0, 10)


def _apply_blocked_discharge(sd: dict, dt: float) -> None:
    """Blocked discharge: water backs up → high pressure, low flow.
    Centrifugal pumps consume minimum power at zero flow."""
    sd["flow_rate"]   = clamp(sd["flow_rate"]   - 5.0 * dt, 0, 0.5)
    sd["pressure"]    = clamp(sd["pressure"]    + 1.5 * dt, 0, 12)
    sd["vibration"]   = clamp(sd["vibration"]   + 0.8 * dt, 0, 15)
    sd["temperature"] = clamp(sd["temperature"] + 0.8 * dt, 0, 130)
    sd["current"]     = clamp(sd["current"]     - 3.0 * dt, 0.5, 70)
    sd["tank_level"]  = clamp(sd["tank_level"]  + 0.1 * dt, 0, 100)


def _apply_pipe_burst(sd: dict, dt: float) -> None:
    """Pipe burst: water escapes → high apparent flow, low pressure, tank drains."""
    sd["flow_rate"]  = clamp(sd["flow_rate"]  + 3.0 * dt, 0, 60)
    sd["pressure"]   = clamp(sd["pressure"]   - 0.8 * dt, 0, 2)
    sd["vibration"]  = clamp(sd["vibration"]  + 0.6 * dt, 0, 15)
    sd["current"]    = clamp(sd["current"]    + 8.0 * dt, 0, 70)
    sd["temperature"] = clamp(sd["temperature"] + 1.0 * dt, 0, 130)
    sd["tank_level"] = clamp(sd["tank_level"] - 5.0 * dt, 0, 100)


def _apply_cavitation(sd: dict, dt: float) -> None:
    sd["flow_rate"]  = clamp(sd["flow_rate"]  + random.uniform(-5, 5) * dt, 0, 60)
    sd["vibration"]  = clamp(sd["vibration"]  + random.uniform(0.5, 2.0) * dt, 0, 15)
    sd["pressure"]   = clamp(sd["pressure"]   + random.uniform(-0.5, 0.5) * dt, 0, 12)
    sd["temperature"] = clamp(sd["temperature"] + 1.2 * dt, 0, 130)


def _apply_overheat(sd: dict, dt: float) -> None:
    """Overheat: temperature rises linearly, vibration increases due to
    bearing wear.  Q, P, I stay normal — the pump keeps pushing water
    while thermally destroying itself."""
    sd["temperature"] = clamp(sd["temperature"] + 2.0 * dt, 0, 130)
    sd["vibration"]   = clamp(sd["vibration"]   + 0.3 * dt, 0, 15)


def _apply_power_surge(sd: dict, dt: float) -> None:
    """Power surge / motor locked rotor: motor seizes, flow stops, current spikes."""
    sd["flow_rate"]   = clamp(sd["flow_rate"]   - 10.0 * dt, 0, 0.5)
    sd["pressure"]    = clamp(sd["pressure"]    - 5.0 * dt, 0, 0.5)
    sd["voltage"]     = clamp(sd["voltage"]     - 15.0 * dt, 180, 260)
    sd["current"]     = clamp(sd["current"]     + 12.0 * dt, 0, 70)
    sd["temperature"] = clamp(sd["temperature"] + 3.0 * dt, 0, 130)
    sd["vibration"]   = clamp(sd["vibration"]   + 1.5 * dt, 0, 15)


def _apply_power_outage(sd: dict, dt: float) -> None:
    """Power outage: voltage/current drop instantly, flow/pressure/vibration
    ramp down smoothly over ~1-2 seconds due to water and motor inertia."""
    sd["voltage"]     = 0.0
    sd["current"]     = 0.0
    sd["flow_rate"]   = clamp(sd["flow_rate"]   - 20.0 * dt, 0, 60)
    sd["pressure"]    = clamp(sd["pressure"]    - 4.0 * dt, 0, 12)
    sd["vibration"]   = clamp(sd["vibration"]   - 5.0 * dt, 0, 15)
    sd["temperature"] = clamp(sd["temperature"] - 0.5 * dt, T_AMBIENT, _TEMP_HIGH)


def _clamp_pump_values(sd: dict) -> None:
    sd["flow_rate"]   = round(clamp(sd["flow_rate"],   _FLOW_LOW,       _FLOW_HIGH),       1)
    sd["pressure"]    = round(clamp(sd["pressure"],    _PRES_LOW,       _PRES_HIGH),       1)
    sd["temperature"] = round(clamp(sd["temperature"], _TEMP_LOW,       _TEMP_HIGH),       1)
    sd["vibration"]   = round(clamp(sd["vibration"],   _VIB_LOW,        _VIB_HIGH),        1)
    sd["voltage"]     = round(clamp(sd["voltage"],     _VOLT_LOW,       _VOLT_HIGH),       1)
    sd["current"]     = round(clamp(sd["current"],     _CURR_LOW,       _CURR_HIGH),       1)
    sd["pump_energy"] = round(clamp(sd["pump_energy"], _PUMP_ENERGY_LOW, _PUMP_ENERGY_HIGH), 1)


def _run_pump_normal(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    # ── Voltage ────────────────────────────────────────────────────────────
    if not is_locked(sim, "voltage"):
        volt = sd["voltage"] + (220.0 - sd["voltage"]) * 0.05 * dt + random.uniform(-0.5, 0.5) * dt
        sd["voltage"] = round(clamp(volt, _VOLT_LOW, _VOLT_HIGH), 1)

    volt = sd["voltage"]

    # Voltage collapse → all outputs drop
    if volt < 50.0:
        if not is_locked(sim, "flow_rate"):
            sd["flow_rate"]  = round(clamp(sd["flow_rate"]  - 5.0 * dt, 0.0, _FLOW_HIGH), 1)
        if not is_locked(sim, "pressure"):
            sd["pressure"]   = round(clamp(sd["pressure"]   - 2.0 * dt, 0.0, _PRES_HIGH), 1)
        if not is_locked(sim, "vibration"):
            sd["vibration"]  = round(clamp(sd["vibration"]  - 2.0 * dt, 0.0, _VIB_HIGH),  1)
        if not is_locked(sim, "current"):
            sd["current"]    = round(clamp(sd["current"]    - 5.0 * dt, 0.0, _CURR_HIGH),  1)
        if not is_locked(sim, "pump_energy"):
            sd["pump_energy"] = round(clamp(sd["pump_energy"] - 1.0 * dt, 0.0, _PUMP_ENERGY_HIGH), 1)
        if not is_locked(sim, "temperature"):
            sd["temperature"] = round(
                clamp(sd["temperature"] + (T_AMBIENT - sd["temperature"]) * 0.02 * dt,
                       _TEMP_LOW, _TEMP_HIGH), 1
            )
        return

    # ── Tank < 10% → cavitation / starvation mode ──────────────────────────
    tank = sd["tank_level"]
    if tank < 10.0:
        if not is_locked(sim, "flow_rate"):
            sd["flow_rate"]   = round(clamp(sd["flow_rate"]   - 3.0 * dt, 0.0, 2.0),   1)
        if not is_locked(sim, "pressure"):
            sd["pressure"]    = round(clamp(sd["pressure"]    - 0.8 * dt, 0.0, 1.0),   1)
        if not is_locked(sim, "vibration"):
            sd["vibration"]   = round(clamp(sd["vibration"]   + 1.2 * dt, 0.5, 15.0),  1)
        if not is_locked(sim, "temperature"):
            sd["temperature"] = round(clamp(sd["temperature"] + 2.0 * dt, _TEMP_LOW, 120.0), 1)
        if not is_locked(sim, "current"):
            sd["current"]     = round(clamp(sd["current"]     - 2.0 * dt, 0.0, 8.0),   1)
        if not is_locked(sim, "pump_energy"):
            sd["pump_energy"] = round(
                _compute_pump_energy(sd["flow_rate"], sd["pressure"], volt), 1
            )
        return

    # ── Normal operating regime ────────────────────────────────────────────
    # MAX demand capped at 16.0 l/s to ensure pressure never drops
    # below the 2.0 bar alert threshold (P = 7.0 - 0.012*16^2 = 3.93 bar).
    _DEMAND_MAX = 16.0
    if is_locked(sim, "flow_rate"):
        flow = sd["flow_rate"]
        sim._pump_demand = clamp(flow, 8.0, _DEMAND_MAX)
    else:
        sim._pump_demand = _rand_walk(sim._pump_demand, 0.5 * dt, 10.0, _DEMAND_MAX)
        flow = sim._pump_demand
        # Ramp flow_rate smoothly from current sensor value toward demand
        # to prevent abrupt jumps when pump comes out of idle
        current_flow = sd.get("flow_rate", 0)
        max_flow_ramp = 3.0 * dt
        if flow > current_flow + max_flow_ramp:
            flow = current_flow + max_flow_ramp
        elif flow < current_flow - max_flow_ramp:
            flow = current_flow - max_flow_ramp

    pressure = max(0.5, PUMP_P0 - PUMP_K * flow ** 2) + random.uniform(-0.1, 0.1) * dt
    # Ramp pressure smoothly from current value toward target
    current_press = sd.get("pressure", 0)
    max_press_ramp = 1.5 * dt
    if pressure > current_press + max_press_ramp:
        pressure = current_press + max_press_ramp
    elif pressure < current_press - max_press_ramp:
        pressure = current_press - max_press_ramp

    # First-order thermal model
    target_temp = 50.0 + (flow * pressure * 0.1)
    temp_diff   = target_temp - sd["temperature"]
    temp = sd["temperature"] + temp_diff * 0.02 * dt + random.uniform(-0.1, 0.1) * dt

    vib  = 0.5 + flow / 25.0 + max(0.0, temp - 65.0) / 40.0 + random.uniform(-0.2, 0.3) * dt
    curr = flow * pressure / (volt * 0.75) + random.uniform(-0.5, 0.5) * dt
    energy = _compute_pump_energy(flow, pressure, volt)

    if not is_locked(sim, "flow_rate"):
        sd["flow_rate"]   = round(clamp(flow,     _FLOW_LOW,       _FLOW_HIGH),       1)
    if not is_locked(sim, "pressure"):
        sd["pressure"]    = round(clamp(pressure, _PRES_LOW,       _PRES_HIGH),       1)
    if not is_locked(sim, "temperature"):
        sd["temperature"] = round(clamp(temp,     _TEMP_LOW,       _TEMP_HIGH),       1)
    if not is_locked(sim, "vibration"):
        sd["vibration"]   = round(clamp(vib,      _VIB_LOW,        _VIB_HIGH),        1)
    if not is_locked(sim, "current"):
        sd["current"]     = round(clamp(curr,     _CURR_LOW,       _CURR_HIGH),       1)
    if not is_locked(sim, "pump_energy"):
        sd["pump_energy"] = round(clamp(energy,   _PUMP_ENERGY_LOW, _PUMP_ENERGY_HIGH), 1)
