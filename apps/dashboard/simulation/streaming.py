import json
import logging

import eventlet
from django.http import StreamingHttpResponse

from apps.core.services.http_response import json_error
from .shared import get_simulator


logger = logging.getLogger(__name__)


def sse_stream(request, building_id: int) -> StreamingHttpResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error("No hay simulador activo para este edificio", 404)

    def event_stream():
        from apps.sensors.payload import build_live_payload_for_sim
        from collections import deque
        client_queue = deque()
        if hasattr(sim.pending_alerts, "subscribers"):
            sim.pending_alerts.subscribers.append(client_queue)
        try:
            while True:
                from apps.sensors.sensor_config import SIM_TICK_INTERVAL
                eventlet.sleep(SIM_TICK_INTERVAL)
                payload = build_live_payload_for_sim(sim)
                yield f"data: {json.dumps(payload)}\n\n"
                while client_queue:
                    notif = client_queue.popleft()
                    yield f"event: history-event\ndata: {json.dumps(notif)}\n\n"
        except (GeneratorExit, IOError, OSError):
            logger.info("Cliente SSE desconectado del edificio %s", building_id)
        finally:
            if hasattr(sim.pending_alerts, "subscribers"):
                try:
                    sim.pending_alerts.subscribers.remove(client_queue)
                except ValueError:
                    pass

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
