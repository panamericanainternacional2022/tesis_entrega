import time

from apps.sensors.simulation.constants import CLEAR_FAULT_MIN_FLOW, CLEAR_FAULT_MIN_PRESSURE, CLEAR_FAULT_MAX_VIBRATION, CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH, CLEAR_FAULT_MAX_LOAD
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.utils import clamp


PROGRESSIVE_DURATION: float = 15.0


def apply_pump_recovery(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    expiration = time.time() + PROGRESSIVE_DURATION
    sim._pump_start_grace_ticks = 5
    if sd.get("flow_rate", 0) < CLEAR_FAULT_MIN_FLOW:
        sim.manual_overrides["flow_rate"] = expiration
        sim.manual_targets["flow_rate"] = CLEAR_FAULT_MIN_FLOW
    if sd.get("pressure", 0) < CLEAR_FAULT_MIN_PRESSURE:
        sim.manual_overrides["pressure"] = expiration
        sim.manual_targets["pressure"] = CLEAR_FAULT_MIN_PRESSURE
    if sd.get("vibration", 0) > CLEAR_FAULT_MAX_VIBRATION:
        sim.manual_overrides["vibration"] = expiration
        sim.manual_targets["vibration"] = CLEAR_FAULT_MAX_VIBRATION
    volt = sd.get("voltage", 220)
    if volt < CLEAR_FAULT_VOLTAGE_LOW or volt > CLEAR_FAULT_VOLTAGE_HIGH:
        sim.manual_overrides["voltage"] = expiration
        sim.manual_targets["voltage"] = clamp(volt, CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH)
    sim._pump_demand = CLEAR_FAULT_MIN_FLOW


def apply_elevator_recovery(sim: BuildingSimulator) -> None:
    from apps.sensors.simulation.physics.elevator import _clear_elevator_fault_params
    sd = sim.sensor_data
    expiration = time.time() + PROGRESSIVE_DURATION
    _clear_elevator_fault_params(sim)
    sd["motor_stuck"] = False
    if sd.get("speed", 0) < 0.0:
        sim.manual_overrides["speed"] = expiration
        sim.manual_targets["speed"] = 0.0
    if sd.get("load", 0) > CLEAR_FAULT_MAX_LOAD:
        sim.manual_overrides["load"] = expiration
        sim.manual_targets["load"] = CLEAR_FAULT_MAX_LOAD
    sd["door_status"] = "closed"
    sim.door_close_attempts = 0
    sim._elev_state = "IDLE"
