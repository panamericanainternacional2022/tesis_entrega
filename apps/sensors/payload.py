from apps.sensors.sensor_config import RATIONING_THRESHOLD
from apps.sensors.services.payload_service import PayloadContext, build_live_payload as _build_live_payload
from apps.sensors.simulation.models import BuildingSimulator


def build_live_payload_for_sim(sim: BuildingSimulator) -> dict:
    ctx = PayloadContext(
        sensor_data=sim.sensor_data,
        history=sim.history,
        door_close_attempts=sim.door_close_attempts,
        pump_on=sim.pump_on,
        elevator_on=sim.elevator_on,
        equipment_types=sim.equipment_types,
        rationing_threshold=RATIONING_THRESHOLD,
        sim_paused=sim.sim_paused,
        sim_speed=sim.sim_speed,
        sim_started=sim.sim_started,
        active_edificio_id=sim.edificio_id,
        django_connected=True,
        sim_faults=sim.sim_faults,
        active_alerts=sim.active_alerts,
    )
    return _build_live_payload(ctx)
