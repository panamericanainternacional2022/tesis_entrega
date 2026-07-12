import random

from apps.sensors.sensor_config import SENSOR_RANGES, PUMP_VARS
from apps.sensors.simulation.constants import (
    PUMP_P0, PUMP_K, T_AMBIENT,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.utils import clamp, is_locked


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
        sd["pump_tank_level"] = round(clamp(sd["pump_tank_level"] + d_tank, sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[0], sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[1]), 1)

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
            clamp(sd["pump_temperature"] - 0.5 * dt, sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1]), 1
        )
    if not is_locked(sim, "pump_voltage"):
        volt = sd["pump_voltage"]
        # Red monofásica disponible aunque el motor esté parado — converge a 220 V (spec: voltage_inicial=220 V)
        volt_diff = 220.0 - volt
        sd["pump_voltage"] = round(
            clamp(
                volt + volt_diff * 0.1 * dt,
                0.0, sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[1],
            ), 1
        )
    if not is_locked(sim, "pump_water_quality"):
        sd["pump_water_quality"] = round(
            clamp(sd.get("pump_water_quality", 200.0) + random.uniform(-1.0, 1.0) * dt, sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[0], sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[1]), 1
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
        handler(sim, temp_sd, dt)

    for k in PUMP_VARS:
        sd[k] = temp_sd[k]

    if fault_type != "power_outage":
        _clamp_pump_values(sim, sd)


def _apply_dry_run(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = clamp(sd["pump_flow_rate"]   - 5.0 * dt, sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0], 0.5)          # converge a casi-cero (0.5 = techo de sequía)
    sd["pump_pressure"]    = clamp(sd["pump_pressure"]    - 2.0 * dt, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0], 0.5)          # idem
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 1.5 * dt, sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1])   # sube sin refrigeración
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + 0.5 * dt, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1])
    sd["pump_current"]     = clamp(sd["pump_current"]     - 2.0 * dt, sim.sensor_limits.get('pump_current', (0.0, 30.0))[0], sim.sensor_limits.get('pump_current', (0.0, 30.0))[1])   # B-4: mín era 1.0 A → ahora 0.0
    sd["pump_tank_level"]  = clamp(sd["pump_tank_level"]  - 15.0 * dt, sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[0], 10.0)        # 10% = umbral crítico-bajo del tanque


def _apply_blocked_discharge(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = clamp(sd["pump_flow_rate"]   - 5.0 * dt, sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0], 0.5)          # flujo cae a casi-cero
    sd["pump_pressure"]    = clamp(sd["pump_pressure"]    + 1.5 * dt, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0], sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[1])   # presión sube a máx (descarga bloqueada)
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + 0.8 * dt, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1])
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 3.0 * dt, sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1])   # fricción hidrodinámica interna
    sd["pump_current"]     = clamp(sd["pump_current"]     + 2.0 * dt, 10.0,      sim.sensor_limits.get('pump_current', (0.0, 30.0))[1])   # 10.0 A = carga mínima con bloqueo
    sd["pump_tank_level"]  = clamp(sd["pump_tank_level"]  + 0.1 * dt, sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[0], sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[1])


def _apply_pipe_burst(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = clamp(sd["pump_flow_rate"]   + 3.0 * dt, sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0], sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[1])
    sd["pump_pressure"]    = clamp(sd["pump_pressure"]    - 0.8 * dt, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0], 2.0)          # 2.0 = presión residual post-ruptura
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + 0.6 * dt, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1])
    sd["pump_current"]     = clamp(sd["pump_current"]     + 8.0 * dt, sim.sensor_limits.get('pump_current', (0.0, 30.0))[0], sim.sensor_limits.get('pump_current', (0.0, 30.0))[1])
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 1.0 * dt, sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1])
    sd["pump_tank_level"]  = clamp(sd["pump_tank_level"]  - 5.0 * dt, sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[0], sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[1])


def _apply_cavitation(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = clamp(sd["pump_flow_rate"]   + random.uniform(-5, 5) * dt,      sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0], sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[1])
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + random.uniform(0.5, 2.0) * dt,  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1])
    # Oscilación brusca de presión — inestabilidad hidrodinámica real (±2.0 bar)
    sd["pump_pressure"]    = clamp(sd["pump_pressure"]    + random.uniform(-2.0, 2.0) * dt, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0], sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[1])
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 1.2 * dt,                      sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1])
    # Picos de corriente por variaciones de carga hidrodinámica
    sd["pump_current"]     = clamp(sd["pump_current"]     + random.uniform(-3.0, 5.0) * dt, sim.sensor_limits.get('pump_current', (0.0, 30.0))[0], sim.sensor_limits.get('pump_current', (0.0, 30.0))[1])


def _apply_overheat(sim, sd: dict, dt: float) -> None:
    # Spec: temp sube linealmente hasta rebasar el Límite Físico (100°C = sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1])
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 2.0 * dt, sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1])   # B-7: antes clampeaba a 130°C
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + 0.3 * dt, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1])
    # Resistencia eléctrica del bobinado aumenta con temperatura (R = R0 * (1 + α*ΔT))
    sd["pump_current"]     = clamp(sd["pump_current"]     + 0.5 * dt, sim.sensor_limits.get('pump_current', (0.0, 30.0))[0], sim.sensor_limits.get('pump_current', (0.0, 30.0))[1])
    # Viscosidad del fluido caliente reduce el caudal
    sd["pump_flow_rate"]   = clamp(sd["pump_flow_rate"]   - 0.3 * dt, sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0], sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[1])


def _apply_power_surge(sim, sd: dict, dt: float) -> None:
    sd["pump_flow_rate"]   = clamp(sd["pump_flow_rate"]   - 10.0 * dt, sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0], 0.5)         # converge a casi-cero durante sobrecarga
    sd["pump_pressure"]    = clamp(sd["pump_pressure"]    - 5.0 * dt,  sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0], 0.5)
    sd["pump_voltage"]     = clamp(sd["pump_voltage"]     - 15.0 * dt, sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[0], sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[1])  # usa rango completo (0–300 V)
    sd["pump_current"]     = clamp(sd["pump_current"]     + 12.0 * dt, sim.sensor_limits.get('pump_current', (0.0, 30.0))[0], sim.sensor_limits.get('pump_current', (0.0, 30.0))[1])  # dispara a crítico (>22 A)
    sd["pump_temperature"] = clamp(sd["pump_temperature"] + 3.0 * dt,  sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1])  # Efecto Joule
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   + 1.5 * dt,  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1])


def _apply_power_outage(sim, sd: dict, dt: float) -> None:
    # Spec: voltage→0, current→0, flow y pressure→0.0 de forma INMEDIATA (B-3)
    sd["pump_voltage"]     = 0.0
    sd["pump_current"]     = 0.0
    sd["pump_flow_rate"]   = 0.0                                                                 # B-3: inmediato (antes: rampa -20*dt)
    sd["pump_pressure"]    = 0.0                                                                 # B-3: inmediato (antes: rampa -4*dt)
    sd["pump_vibration"]   = clamp(sd["pump_vibration"]   - 5.0 * dt, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1])
    sd["pump_temperature"] = clamp(sd["pump_temperature"] - 0.5 * dt, T_AMBIENT, sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1])

def _apply_bearing_failure(sim, sd: dict, dt: float) -> None:
    sd["pump_vibration"]     = clamp(sd["pump_vibration"]     + 1.5 * dt,  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],  sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1])
    sd["pump_temperature"]   = clamp(sd["pump_temperature"]   + 3.0 * dt,  sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1])
    sd["pump_current"]       = clamp(sd["pump_current"]       + 4.0 * dt,  10.0,      sim.sensor_limits.get('pump_current', (0.0, 30.0))[1])   # 10.0 A = carga mínima por fricción parásita
    sd["pump_water_quality"] = clamp(sd.get("pump_water_quality", 200.0) + 15.0 * dt, sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[0], sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[1])
    # Pérdida de eficiencia mecánica → degradación progresiva de caudal y presión
    sd["pump_flow_rate"]     = clamp(sd["pump_flow_rate"]     - 0.4 * dt,  sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0], sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[1])
    sd["pump_pressure"]      = clamp(sd["pump_pressure"]      - 0.2 * dt,  sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0], sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[1])

def _clamp_pump_values(sim, sd: dict) -> None:
    sd["pump_flow_rate"]   = round(clamp(sd["pump_flow_rate"],   sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0],       sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[1]),       1)
    sd["pump_pressure"]    = round(clamp(sd["pump_pressure"],    sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0],       sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[1]),       1)
    sd["pump_temperature"] = round(clamp(sd["pump_temperature"], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0],       sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1]),       1)
    sd["pump_vibration"]   = round(clamp(sd["pump_vibration"],   sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],        sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1]),        1)
    sd["pump_voltage"]     = round(clamp(sd["pump_voltage"],     sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[0],       sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[1]),       1)
    sd["pump_current"]     = round(clamp(sd["pump_current"],     sim.sensor_limits.get('pump_current', (0.0, 30.0))[0],       sim.sensor_limits.get('pump_current', (0.0, 30.0))[1]),       1)
    sd["pump_water_quality"] = round(clamp(sd.get("pump_water_quality", 200.0), sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[0], sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[1]), 1)


def _run_pump_normal(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    # ── Voltage ────────────────────────────────────────────────────────────
    if not is_locked(sim, "pump_voltage"):
        volt = sd["pump_voltage"] + (220.0 - sd["pump_voltage"]) * 0.05 * dt + random.uniform(-0.5, 0.5) * dt
        sd["pump_voltage"] = round(clamp(volt, sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[0], sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[1]), 1)

    volt = sd["pump_voltage"]

    # Voltage collapse → all outputs drop
    if volt < 50.0:
        if not is_locked(sim, "pump_flow_rate"):
            sd["pump_flow_rate"]  = round(clamp(sd["pump_flow_rate"]  - 5.0 * dt, 0.0, sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[1]), 1)
        if not is_locked(sim, "pump_pressure"):
            sd["pump_pressure"]   = round(clamp(sd["pump_pressure"]   - 2.0 * dt, 0.0, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[1]), 1)
        if not is_locked(sim, "pump_vibration"):
            sd["pump_vibration"]  = round(clamp(sd["pump_vibration"]  - 2.0 * dt, 0.0, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1]),  1)
        if not is_locked(sim, "pump_current"):
            sd["pump_current"]    = round(clamp(sd["pump_current"]    - 5.0 * dt, 0.0, sim.sensor_limits.get('pump_current', (0.0, 30.0))[1]),  1)
        if not is_locked(sim, "pump_temperature"):
            sd["pump_temperature"] = round(
                clamp(sd["pump_temperature"] + (T_AMBIENT - sd["pump_temperature"]) * 0.02 * dt,
                       sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1]), 1
            )
        return

    # ── Tank < 10% → cavitation / starvation mode ──────────────────────────
    tank = sd["pump_tank_level"]
    if tank < 10.0:
        if not is_locked(sim, "pump_flow_rate"):
            sd["pump_flow_rate"]   = round(clamp(sd["pump_flow_rate"]   - 3.0 * dt, sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0], 2.0),        1)  # 2.0 = techo de inanición
        if not is_locked(sim, "pump_pressure"):
            sd["pump_pressure"]    = round(clamp(sd["pump_pressure"]    - 0.8 * dt, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0], 1.0),        1)  # 1.0 bar = presión residual
        if not is_locked(sim, "pump_vibration"):
            sd["pump_vibration"]   = round(clamp(sd["pump_vibration"]   + 1.2 * dt, 0.5, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1]),        1)  # 0.5 = vibración mínima en cavitación
        if not is_locked(sim, "pump_temperature"):
            sd["pump_temperature"] = round(clamp(sd["pump_temperature"] + 2.0 * dt, sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1]), 1)
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
    # Modelo eléctrico ajustado: nominal ~13 A @ 13 l/s, 5 bar, 220 V
    # Opción A: ecuación recalibrada para que el régimen normal quede dentro del umbral (<16 A)
    curr = (flow * pressure * 28.0 + pressure * 120.0) / (volt * 0.85) + random.uniform(-0.5, 0.5) * dt

    if not is_locked(sim, "pump_flow_rate"):
        sd["pump_flow_rate"]   = round(clamp(flow,     sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[0],       sim.sensor_limits.get('pump_flow_rate', (0.0, 60.0))[1]),       1)
    if not is_locked(sim, "pump_pressure"):
        sd["pump_pressure"]    = round(clamp(pressure, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0],       sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[1]),       1)
    if not is_locked(sim, "pump_temperature"):
        sd["pump_temperature"] = round(clamp(temp,     sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[0],       sim.sensor_limits.get('pump_temperature', (-10.0, 100.0))[1]),       1)
    if not is_locked(sim, "pump_vibration"):
        sd["pump_vibration"]   = round(clamp(vib,      sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[0],        sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1]),        1)
    if not is_locked(sim, "pump_current"):
        sd["pump_current"]     = round(clamp(curr,     sim.sensor_limits.get('pump_current', (0.0, 30.0))[0],       sim.sensor_limits.get('pump_current', (0.0, 30.0))[1]),       1)
    if not is_locked(sim, "pump_water_quality"):
        qual = sd.get("pump_water_quality", 200.0)
        qual += (200.0 - qual) * 0.05 * dt + random.uniform(-2.0, 2.0) * dt
        sd["pump_water_quality"] = round(clamp(qual, sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[0], sim.sensor_limits.get('pump_water_quality', (0.0, 1000.0))[1]), 1)
