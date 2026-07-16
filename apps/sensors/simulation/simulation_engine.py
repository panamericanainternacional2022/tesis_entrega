import logging

from apps.sensors.simulation.models import BuildingSimulator

logger = logging.getLogger(__name__)


def update_sensor_data(active_sim: BuildingSimulator) -> None:
    if active_sim.sim_paused:
        return
    if active_sim.has_pump:
        from apps.sensors.simulation.physics.pump import _update_pump
        _update_pump(active_sim)
    if active_sim.has_elevator:
        from apps.sensors.simulation.physics.elevator import _update_elevator
        _update_elevator(active_sim)

