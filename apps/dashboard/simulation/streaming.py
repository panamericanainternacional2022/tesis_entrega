import json
import logging

import eventlet
from django.http import StreamingHttpResponse

from apps.core.services.http_response import json_error
from .shared import get_simulator


logger = logging.getLogger(__name__)


def sse_stream(request, building_id: int = None) -> StreamingHttpResponse:
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return json_error("No autorizado", 401)
        
    rol = request.session.get("usuario_rol", "US")
    sim = None
    
    if building_id:
        sim = get_simulator(building_id)
        if sim is None:
            return json_error("No hay simulador activo para este edificio", 404)

    def event_stream():
        from apps.sensors.payload import build_live_payload_for_sim
        from apps.history.shared import _build_history_query
        from apps.sensors.sensor_config import SIM_TICK_INTERVAL
        from collections import deque
        
        client_queue = deque()
        if sim and hasattr(sim.pending_alerts, "subscribers"):
            sim.pending_alerts.subscribers.append(client_queue)
            
        last_count = -1

        try:
            import time
            last_telemetry = 0
            
            while True:
                now = time.time()
                force_count_update = False
                
                # Despachar eventos de historial INMEDIATAMENTE
                if sim:
                    while client_queue:
                        notif = client_queue.popleft()
                        yield f"event: history-event\ndata: {json.dumps(notif)}\n\n"
                        force_count_update = True
                        
                # Telemetría cada SIM_TICK_INTERVAL
                if now - last_telemetry >= SIM_TICK_INTERVAL:
                    if sim:
                        payload = build_live_payload_for_sim(sim)
                        yield f"data: {json.dumps(payload)}\n\n"
                    force_count_update = True
                    last_telemetry = now
                    
                # 2. Conteo global de historial (sólo consultar DB si hubo un tick o alerta nueva)
                if force_count_update:
                    records, _ = _build_history_query(usuario_id, rol)
                    count = records.filter(resolved=False).distinct().count()
                    
                    if count != last_count:
                        yield f"event: count-update\ndata: {json.dumps({'count': count})}\n\n"
                        last_count = count

                eventlet.sleep(0.1)

        except (GeneratorExit, IOError, OSError):
            logger.info("Cliente SSE desconectado (usuario %s)", usuario_id)
        finally:
            if sim and hasattr(sim.pending_alerts, "subscribers"):
                try:
                    sim.pending_alerts.subscribers.remove(client_queue)
                except ValueError:
                    pass

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
