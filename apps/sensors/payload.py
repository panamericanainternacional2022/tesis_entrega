from apps.sensors.services.payload_service import PayloadContext, build_live_payload as _build_live_payload
from apps.sensors.simulation.models import BuildingSimulator


def build_live_payload_for_sim(sim: BuildingSimulator) -> dict:
    ctx = PayloadContext(
        sensor_data=sim.sensor_data,
        history=sim.history,
        pump_on=sim.pump_on,
        elevator_on=sim.elevator_on,
        equipment_types=sim.equipment_types,
        sim_paused=sim.sim_paused,
        sim_speed=sim.sim_speed,
        sim_started=sim.sim_started,
        active_edificio_id=sim.edificio_id,
        django_connected=True,
        sim_faults=sim.sim_faults,
        elev_state=getattr(sim, '_elev_state', None),
        elev_target_floor=getattr(sim, '_elev_target_floor', None),
        elev_direction=getattr(sim, '_elev_direction', None),
        pump_demand=getattr(sim, '_pump_demand', None),
        fault_injected_at=getattr(sim, 'fault_injected_at', None),
    )
    return _build_live_payload(ctx)
