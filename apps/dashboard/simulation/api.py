import json
import logging
from typing import Any

from django.http import JsonResponse

from .shared import get_simulator, get_first_simulator
from apps.core.services.http_response import json_error

logger = logging.getLogger(__name__)


def api_status(request) -> JsonResponse:
    building_id = request.GET.get("edificio_id")
    if building_id:
        try:
            building_id = int(building_id)
        except (ValueError, TypeError):
            return json_error("edificio_id inválido")
    else:
        first_sim = get_first_simulator()
        if not first_sim:
            return json_error("No hay simuladores activos", 404)
        building_id = first_sim.edificio_id

    sim = get_simulator(building_id)
    if sim is None:
        return json_error("No hay simulador activo para este edificio", 404)

    from apps.sensors.payload import build_live_payload_for_sim
    return JsonResponse(build_live_payload_for_sim(sim))
