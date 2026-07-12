import time

from apps.sensors.simulation.constants import CLEAR_FAULT_MIN_FLOW, CLEAR_FAULT_MIN_PRESSURE, CLEAR_FAULT_MAX_VIBRATION, CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH, CLEAR_FAULT_MAX_LOAD
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.utils import clamp


PROGRESSIVE_DURATION: float = 15.0


def apply_pump_recovery(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    expiration = time.time() + PROGRESSIVE_DURATION
    sim._pump_start_grace_ticks = 5
    if sd.get("pump_flow_rate", 0) < CLEAR_FAULT_MIN_FLOW:
        sim.manual_overrides["pump_flow_rate"] = expiration
        sim.manual_targets["pump_flow_rate"] = CLEAR_FAULT_MIN_FLOW
    if sd.get("pump_pressure", 0) < CLEAR_FAULT_MIN_PRESSURE:
        sim.manual_overrides["pump_pressure"] = expiration
        sim.manual_targets["pump_pressure"] = CLEAR_FAULT_MIN_PRESSURE
    if sd.get("pump_vibration", 0) > CLEAR_FAULT_MAX_VIBRATION:
        sim.manual_overrides["pump_vibration"] = expiration
        sim.manual_targets["pump_vibration"] = CLEAR_FAULT_MAX_VIBRATION
    volt = sd.get("pump_voltage", 220)
    if volt < CLEAR_FAULT_VOLTAGE_LOW or volt > CLEAR_FAULT_VOLTAGE_HIGH:
        sim.manual_overrides["pump_voltage"] = expiration
        sim.manual_targets["pump_voltage"] = clamp(volt, CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH)
    sim._pump_demand = CLEAR_FAULT_MIN_FLOW


def apply_elevator_recovery(sim: BuildingSimulator) -> None:
    from apps.sensors.simulation.physics.elevator import _clear_elevator_fault_params
    sd = sim.sensor_data
    expiration = time.time() + PROGRESSIVE_DURATION
    _clear_elevator_fault_params(sim)
    if sd.get("elev_speed", 0) < 0.0:
        sim.manual_overrides["elev_speed"] = expiration
        sim.manual_targets["elev_speed"] = 0.0
    if sd.get("elev_load", 0) > CLEAR_FAULT_MAX_LOAD:
        sim.manual_overrides["elev_load"] = expiration
        sim.manual_targets["elev_load"] = CLEAR_FAULT_MAX_LOAD
    sd["elev_door_status"] = "closed"
    sim._elev_state = "IDLE"
