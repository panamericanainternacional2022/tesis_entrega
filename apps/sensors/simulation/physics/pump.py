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
    "pump_flow_rate":     5.0,    # l/s/tick
    "pump_pressure":      3.0,    # bar/tick
    "pump_temperature":   2.5,    # °C/tick  - Inercia térmica (calentamiento/enfriamiento progresivo)
    "pump_vibration":     3.0,    # mm/s/tick
    "pump_current":       8.0,    # A/tick   - Respuesta eléctrica rápida
    "pump_voltage":       220.0,  # V/tick   - Escalón prácticamente instantáneo
    "pump_tank_level":    1.0,    # %/tick   - Dinámica de masa lenta
    "pump_water_quality": 15.0,   # ppm/tick - Disolución/arrastre progresivo
}


def _rand_walk(current: float, step: float, lo: float, hi: float) -> float:
    return clamp(current + random.uniform(-step, step), lo, hi)


def _update_pump(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed

    # ── Tank level physics (solo en operación normal sin fallas activas) ─────
    if sim.pump_on and "pump" not in sim.sim_faults:
        from apps.thresholds.services import get_thresholds
        thresh = get_thresholds(sim.edificio_id)
        inflow = sd.get("pump_flow_rate", 0.0)

        flow_high = thresh.get("pump_flow_rate", {}).get("high", 18.0)
        target_max = max(5.0, flow_high * 0.85)
        target_min = max(0.0, target_max - 5.0)
        outflow = (target_max + target_min) / 2.0 + random.uniform(-1.0, 1.0)

        net = inflow - outflow
        d_tank = net * 0.05 * dt + random.uniform(-0.1, 0.1) * dt
        
        new_tank = sd["pump_tank_level"] + d_tank
        
        tank_t = thresh.get("pump_tank_level", {})
        safe_tank_min = tank_t.get("high", 20.0) + (tank_t.get("critic", 90.0) - tank_t.get("high", 20.0)) * 0.25
        safe_tank_max = tank_t.get("critic", 90.0) - (tank_t.get("critic", 90.0) - tank_t.get("high", 20.0)) * 0.25
        if new_tank < safe_tank_min:
            new_tank = min(safe_tank_min, new_tank + 5.0 * dt)
        elif new_tank > safe_tank_max:
            new_tank = max(safe_tank_max, new_tank - 5.0 * dt)
        
        sd["pump_tank_level"] = round(clamp(new_tank, sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[0], sim.sensor_limits.get('pump_tank_level', (0.0, 100.0))[1]), 1)

    # Recovery countdown
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


def _get_pump_thresholds(sim: BuildingSimulator) -> dict:
    """Obtiene los umbrales del edificio en caché o los carga frescos."""
    try:
        from apps.thresholds.services import get_thresholds
        return get_thresholds(sim.edificio_id)
    except Exception:
        return {}


def _thresh_critic(thresh: dict, var: str, default: float) -> float:
    """Devuelve el valor del umbral crítico para la variable dada."""
    return thresh.get(var, {}).get("critic", default)


def _thresh_high(thresh: dict, var: str, default: float) -> float:
    """Devuelve el valor del umbral alto para la variable dada."""
    return thresh.get(var, {}).get("high", default)


def _above_critic(thresh: dict, var: str, default_critic: float, factor: float = 1.1) -> float:
    """Devuelve un valor que supera el umbral crítico por un factor, acotado al límite físico."""
    return _thresh_critic(thresh, var, default_critic) * factor


def _apply_pump_fault(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    fault_type = sim.sim_faults.get("pump")

    temp_sd = sd.copy()
    thresh = _get_pump_thresholds(sim)

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
        handler(sim, temp_sd, dt, thresh)

    all_reached = True
    for k in PUMP_VARS:
        target = temp_sd[k]
        bounds = sim.sensor_limits.get(k)
        if bounds:
            target = max(bounds[0], min(bounds[1], target))

        rate = PUMP_RAMP_RATES.get(k, 2.0)
        if not _ramp_toward_target(sd, k, target, rate, dt):
            all_reached = False

    if fault_type == "cavitation":
        sd["pump_flow_rate"]   = round(clamp(temp_sd["pump_flow_rate"], 0.0, 50000.0), 1)
        sd["pump_pressure"]    = round(clamp(temp_sd["pump_pressure"], 0.0, 10.0), 1)
        sd["pump_current"]     = round(clamp(temp_sd["pump_current"], 0.0, 30.0), 1)
        sd["pump_vibration"]   = round(clamp(temp_sd["pump_vibration"], 0.0, 15.0), 1)

    if fault_type != "power_outage":
        _clamp_pump_values(sim, sd)

    sim.fault_transition_pump = "stable" if all_reached else "injecting"


def _apply_dry_run(sim, sd: dict, dt: float, thresh: dict) -> None:
    """Sequía (Marcha en seco): Caudal=0, Presión=0, Nivel Tanque=0%, Corriente=Muy Baja (Sin carga ~3.5A), Temp y Vib Altas."""
    lim = sim.sensor_limits
    sd["pump_flow_rate"]   = 0.0
    sd["pump_pressure"]    = 0.0
    sd["pump_tank_level"]  = 0.0
    
    temp_critic = _thresh_critic(thresh, "pump_temperature", 85.0)
    sd["pump_temperature"] = min(lim.get("pump_temperature", (22.0, 100.0))[1], temp_critic * 1.15)
    
    vib_critic = _thresh_critic(thresh, "pump_vibration", 7.1)
    sd["pump_vibration"]   = min(lim.get("pump_vibration", (0.0, 15.0))[1], vib_critic * 1.25)
    
    sd["pump_current"]     = 3.5


def _apply_blocked_discharge(sim, sd: dict, dt: float, thresh: dict) -> None:
    """Descarga Bloqueada (Deadheading): Presión=Pico Máximo, Caudal=0, Temp=Muy Alta, Corriente=Baja (~8.5A), Nivel=Estático."""
    lim = sim.sensor_limits
    sd["pump_flow_rate"]   = 0.0
    
    press_critic = _thresh_critic(thresh, "pump_pressure", 8.0)
    sd["pump_pressure"]    = min(lim.get("pump_pressure", (0.0, 10.0))[1], press_critic * 1.25)
    
    temp_critic = _thresh_critic(thresh, "pump_temperature", 85.0)
    sd["pump_temperature"] = min(lim.get("pump_temperature", (22.0, 100.0))[1], temp_critic * 1.25)
    
    vib_critic = _thresh_critic(thresh, "pump_vibration", 7.1)
    sd["pump_vibration"]   = min(lim.get("pump_vibration", (0.0, 15.0))[1], vib_critic * 1.15)
    
    sd["pump_current"]     = 8.5


def _apply_pipe_burst(sim, sd: dict, dt: float, thresh: dict) -> None:
    """Ruptura de Tubería: Caudal=Pico Máximo, Presión=0, Corriente=Alta (Carga Máxima), Turbidez=Alta, Tanque baja a 0%."""
    lim = sim.sensor_limits
    flow_critic = _thresh_critic(thresh, "pump_flow_rate", 22.0)
    sd["pump_flow_rate"]   = min(lim.get("pump_flow_rate", (0.0, 50000.0))[1], flow_critic * 1.30)
    sd["pump_pressure"]    = 0.0
    
    curr_critic = _thresh_critic(thresh, "pump_current", 22.0)
    sd["pump_current"]     = min(lim.get("pump_current", (0.0, 30.0))[1], curr_critic * 1.15)
    
    vib_critic = _thresh_critic(thresh, "pump_vibration", 7.1)
    sd["pump_vibration"]   = min(lim.get("pump_vibration", (0.0, 15.0))[1], vib_critic * 1.20)
    
    qual_critic = _thresh_critic(thresh, "pump_water_quality", 500.0)
    sd["pump_water_quality"] = min(lim.get("pump_water_quality", (0.0, 1000.0))[1], qual_critic * 1.25)
    
    sd["pump_tank_level"]  = 0.0


def _apply_cavitation(sim, sd: dict, dt: float, thresh: dict) -> None:
    """Cavitación: Presión y Caudal oscilantes/bajos, Vibración=Pico Extremo, Corriente=Inestable/baja, Turbidez=Alta."""
    lim = sim.sensor_limits
    
    sd["pump_flow_rate"]   = random.uniform(1.5, 4.5)
    sd["pump_pressure"]    = random.uniform(0.1, 0.6)
    
    vib_critic = _thresh_critic(thresh, "pump_vibration", 7.1)
    sd["pump_vibration"]   = min(lim.get("pump_vibration", (0.0, 15.0))[1], vib_critic * 1.45 + random.uniform(-0.4, 0.4))
    
    sd["pump_current"]     = random.uniform(7.5, 10.5)
    
    qual_critic = _thresh_critic(thresh, "pump_water_quality", 500.0)
    sd["pump_water_quality"] = min(lim.get("pump_water_quality", (0.0, 1000.0))[1], qual_critic * 1.20)
    
    temp_critic = _thresh_critic(thresh, "pump_temperature", 85.0)
    sd["pump_temperature"] = min(lim.get("pump_temperature", (22.0, 100.0))[1], temp_critic * 1.05)


def _apply_overheat(sim, sd: dict, dt: float, thresh: dict) -> None:
    """Sobrecalentamiento: Temperatura=Pico Crítico, Corriente=Ligeramente Alta, Presión/Caudal=Normales o leve degradación."""
    lim = sim.sensor_limits
    temp_critic = _thresh_critic(thresh, "pump_temperature", 85.0)
    sd["pump_temperature"] = min(lim.get("pump_temperature", (22.0, 100.0))[1], temp_critic * 1.20)
    
    vib_critic = _thresh_critic(thresh, "pump_vibration", 7.1)
    sd["pump_vibration"]   = min(lim.get("pump_vibration", (0.0, 15.0))[1], vib_critic * 1.15)
    
    curr_critic = _thresh_critic(thresh, "pump_current", 22.0)
    sd["pump_current"]     = min(lim.get("pump_current", (0.0, 30.0))[1], curr_critic * 1.05)
    
    base_demand = getattr(sim, "_pump_demand", 12.0)
    degraded_flow = base_demand * 0.95
    sd["pump_flow_rate"]   = min(lim.get("pump_flow_rate", (0.0, 50000.0))[1], degraded_flow)
    degraded_press = max(0.5, PUMP_P0 - PUMP_K * (degraded_flow ** 2)) * 0.95
    sd["pump_pressure"]    = min(lim.get("pump_pressure", (0.0, 10.0))[1], degraded_press)


def _apply_power_surge(sim, sd: dict, dt: float, thresh: dict) -> None:
    """Sobrecarga Eléctrica: Corriente=Pico Crítico (I > I_nom), Voltaje=Caída puntual (Sag), Temp Motor=Muy Alta, Caudal/Presión cayendo a cero."""
    lim = sim.sensor_limits
    
    curr_critic = _thresh_critic(thresh, "pump_current", 22.0)
    sd["pump_current"]     = min(lim.get("pump_current", (0.0, 30.0))[1], curr_critic * 1.25)
    
    sd["pump_voltage"]     = 185.0
    
    temp_critic = _thresh_critic(thresh, "pump_temperature", 85.0)
    sd["pump_temperature"] = min(lim.get("pump_temperature", (22.0, 100.0))[1], temp_critic * 1.15)
    
    vib_critic = _thresh_critic(thresh, "pump_vibration", 7.1)
    sd["pump_vibration"]   = min(lim.get("pump_vibration", (0.0, 15.0))[1], vib_critic * 1.10)
    
    sd["pump_flow_rate"]   = 0.0
    sd["pump_pressure"]    = 0.0


def _apply_power_outage(sim, sd: dict, dt: float, thresh: dict) -> None:
    """Corte Eléctrico: Voltaje=0, Corriente=0, Presión=0, Caudal=0, Vibración=0, Temp=Enfriamiento progresivo hacia T_AMBIENT."""
    sd["pump_voltage"]     = 0.0
    sd["pump_current"]     = 0.0
    sd["pump_flow_rate"]   = 0.0
    sd["pump_pressure"]    = 0.0
    sd["pump_vibration"]   = 0.0
    
    current_temp = sd.get("pump_temperature", T_AMBIENT)
    cooling_step = (current_temp - T_AMBIENT) * 0.08 * dt
    sd["pump_temperature"] = round(max(T_AMBIENT, current_temp - cooling_step), 1)


def _apply_bearing_failure(sim, sd: dict, dt: float, thresh: dict) -> None:
    """Falla de Rodamientos: Vibración=Pico Extremo progresivo, Corriente=Sube por roce, Temp=Alta, Turbidez=Alta, Flujo/Presión leve caída paulatina."""
    lim = sim.sensor_limits
    
    vib_critic = _thresh_critic(thresh, "pump_vibration", 7.1)
    sd["pump_vibration"]   = min(lim.get("pump_vibration", (0.0, 15.0))[1], vib_critic * 1.35)
    
    temp_critic = _thresh_critic(thresh, "pump_temperature", 85.0)
    sd["pump_temperature"] = min(lim.get("pump_temperature", (22.0, 100.0))[1], temp_critic * 1.12)
    
    curr_critic = _thresh_critic(thresh, "pump_current", 22.0)
    sd["pump_current"]     = min(lim.get("pump_current", (0.0, 30.0))[1], curr_critic * 1.08)
    
    qual_critic = _thresh_critic(thresh, "pump_water_quality", 500.0)
    sd["pump_water_quality"] = min(lim.get("pump_water_quality", (0.0, 1000.0))[1], qual_critic * 1.20)
    
    base_demand = getattr(sim, "_pump_demand", 12.0)
    degraded_flow = base_demand * 0.90
    sd["pump_flow_rate"]   = min(lim.get("pump_flow_rate", (0.0, 50000.0))[1], degraded_flow)
    degraded_press = max(0.5, PUMP_P0 - PUMP_K * (degraded_flow ** 2)) * 0.90
    sd["pump_pressure"]    = min(lim.get("pump_pressure", (0.0, 10.0))[1], degraded_press)

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
    
    # ── Voltage ────────────────────────────────────────────────────────────
    volt = sd["pump_voltage"] + (220.0 - sd["pump_voltage"]) * 0.05 * dt + random.uniform(-0.5, 0.5) * dt
    sd["pump_voltage"] = round(clamp(volt, sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[0], sim.sensor_limits.get('pump_voltage', (0.0, 300.0))[1]), 1)

    volt = sd["pump_voltage"]

    # Voltage collapse → all outputs drop
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

    # ── Tank < 10% → cavitation / starvation mode ──────────────────────────
    tank = sd["pump_tank_level"]
    if tank < 10.0:
        sd["pump_flow_rate"]   = round(clamp(sd["pump_flow_rate"]   - 3.0 * dt, sim.sensor_limits.get('pump_flow_rate', (0.0, 50000.0))[0], 2.0),        1)
        sd["pump_pressure"]    = round(clamp(sd["pump_pressure"]    - 0.8 * dt, sim.sensor_limits.get('pump_pressure', (0.0, 10.0))[0], 1.0),        1)
        sd["pump_vibration"]   = round(clamp(sd["pump_vibration"]   + 1.2 * dt, 0.5, sim.sensor_limits.get('pump_vibration', (0.0, 15.0))[1]),        1)
        sd["pump_temperature"] = round(clamp(sd["pump_temperature"] + 2.0 * dt, sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[0], sim.sensor_limits.get('pump_temperature', (22.0, 100.0))[1]), 1)
        sd["pump_current"]     = round(clamp(sd["pump_current"]     - 2.0 * dt, 0.0, 8.0),   1)
        return

    # ── Normal operating regime ────────────────────────────────────────────
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

