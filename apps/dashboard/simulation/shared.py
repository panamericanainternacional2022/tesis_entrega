import json
import logging
import time
from typing import Any


from apps.sensors.simulation.exceptions import SimulatorError
from apps.sensors.simulation.models import BuildingSimulator

logger = logging.getLogger(__name__)

_EQUIPMENT_SYNC_INTERVAL = 60


def get_simulator(building_id: int) -> BuildingSimulator | None:
    from apps.sensors.simulation.globals import simulators

    sim = simulators.get(building_id)
    if sim:
        _maybe_sync_equipment(sim, building_id)
        return sim

    from apps.buildings.models import Building, MonitoringEquipment
    try:
        building = Building.objects.get(pk=building_id)
        equipos = MonitoringEquipment.objects.filter(building_id=building_id)
        if equipos.exists():
            # Double check in case another greenlet registered it during database yields
            sim_already = simulators.get(building_id)
            if sim_already:
                _maybe_sync_equipment(sim_already, building_id)
                return sim_already

            sim = BuildingSimulator(building_id, building.name, floors=building.floors)
            for eq in equipos:
                sim.equipment_types.add(eq.equipment_type)
            sim.has_pump = "bomba" in sim.equipment_types
            sim.has_elevator = "elevador" in sim.equipment_types
            sim.pump_on = False
            sim.elevator_on = False

            simulators[building_id] = sim
            logger.info("Simulador de edificio %s (%s) creado dinámicamente", building_id, building.name)
            return sim
    except Exception as e:
        logger.warning("Error al inicializar simulador dinámico para ID %s: %s", building_id, e)

    logger.warning("No hay simulador disponible para el ID %s", building_id)
    return None


def _maybe_sync_equipment(sim: BuildingSimulator, building_id: int) -> None:
    now = time.time()
    last_sync = getattr(sim, "_last_equipment_sync", 0)
    if now - last_sync < _EQUIPMENT_SYNC_INTERVAL:
        return
    sim._last_equipment_sync = now
    _sync_equipment_from_db(sim, building_id)


def _sync_equipment_from_db(sim: BuildingSimulator, building_id: int) -> None:
    from apps.buildings.models import MonitoringEquipment
    try:
        db_types = set(
            MonitoringEquipment.objects
            .filter(building_id=building_id)
            .values_list("equipment_type", flat=True)
        )
    except Exception as e:
        logger.debug("Error al leer equipos para edificio %s: %s", building_id, e)
        return

    if sim.equipment_types == db_types:
        return

    sim.equipment_types.clear()
    sim.equipment_types.update(db_types)
    sim.has_pump = "bomba" in db_types
    sim.has_elevator = "elevador" in db_types

    if not sim.has_pump:
        sim.pump_on = False
    if not sim.has_elevator:
        sim.elevator_on = False

    logger.info(
        "Equipos sincronizados para edificio %s: %s (pump=%s, elevator=%s)",
        building_id, db_types, sim.has_pump, sim.has_elevator,
    )


def get_first_simulator() -> BuildingSimulator | None:
    from apps.sensors.simulation.globals import simulators
    return next(iter(simulators.values()), None)


def parse_json_body(request) -> dict[str, Any]:
    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        raise SimulatorError("JSON inválido", 400)
