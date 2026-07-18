import logging
import math

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_ok, json_error
from apps.sensors.simulation.exceptions import SimulatorError
from .shared import get_simulator, parse_json_body

logger = logging.getLogger(__name__)


@login_required
def sim_status(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error("No hay simulador activo para este edificio", 404)

    return JsonResponse({
        "edificio_id": sim.edificio_id,
        "nombre": sim.nombre,
        "paused": sim.sim_paused,
        "started": sim.sim_started,
        "speed": sim.sim_speed,
        "pump_on": sim.pump_on,
        "elevator_on": sim.elevator_on,
        "has_pump": sim.has_pump,
        "has_elevator": sim.has_elevator,
        "faults": dict(sim.sim_faults),
        "auto_faults_enabled": sim.auto_faults_enabled,
    })


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_pause(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        paused = body.get("paused")
        if paused is not None:
            sim.sim_paused = bool(paused)
        else:
            sim.sim_paused = not sim.sim_paused
    except (SimulatorError, Exception):
        sim.sim_paused = not sim.sim_paused

    if not sim.sim_paused and not sim.sim_started:
        sim.sim_started = True

    return json_ok({"paused": sim.sim_paused, "started": sim.sim_started, "pump_on": sim.pump_on, "elevator_on": sim.elevator_on, "faults": dict(sim.sim_faults)})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_reset(request, building_id: int) -> JsonResponse:
    from apps.sensors.simulation.controls import reset_simulator

    try:
        message = reset_simulator(building_id)
        return json_ok({
            "message": message,
            "pump_on": True,
            "elevator_on": True,
            "faults": {},
            "speed": 1.0,
            "paused": True,
            "started": False,
            "auto_faults_enabled": False,
        })
    except SimulatorError as e:
        return json_error(e.message, e.status_code)


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_inject_fault(request, building_id: int) -> JsonResponse:
    try:
        body = parse_json_body(request)
    except SimulatorError as e:
        return json_error(e.message, e.status_code)

    device = body.get("device")
    fault_type = body.get("fault_type")
    if not device or not fault_type:
        return json_error("Faltan campos: device, fault_type")

    from apps.sensors.simulation.controls import clear_fault, inject_fault

    try:
        clear_fault(building_id, device)
        message = inject_fault(building_id, device, fault_type)
        sim = get_simulator(building_id)
        if device == "pump":
            sim._protection_grace_ticks_pump = 0
        else:
            sim._protection_grace_ticks_elev = 0
        return json_ok({"message": message, "faults": dict(sim.sim_faults)})
    except SimulatorError as e:
        return json_error(e.message)


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_clear_fault(request, building_id: int) -> JsonResponse:
    try:
        body = parse_json_body(request)
    except SimulatorError as e:
        return json_error(e.message, e.status_code)

    device = body.get("device")

    from apps.sensors.simulation.controls import clear_fault

    try:
        message = clear_fault(building_id, device)
        sim = get_simulator(building_id)
        return json_ok({"message": message, "faults": dict(sim.sim_faults)})
    except SimulatorError as e:
        return json_error(e.message, e.status_code)


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_set_speed(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        speed = float(body.get("speed", 1.0))
        if math.isnan(speed) or math.isinf(speed) or speed <= 0:
            return json_error("Velocidad inválida (NaN, Infinito o menor/igual a 0)")
    except (SimulatorError, ValueError, TypeError):
        return json_error("JSON inválido o speed no numérico")

    from apps.sensors.simulation.constants import MIN_SIM_SPEED, MAX_SIM_SPEED
    sim.sim_speed = max(MIN_SIM_SPEED, min(MAX_SIM_SPEED, speed))
    return json_ok({"speed": sim.sim_speed})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_toggle_pump(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        pump_on = body.get("on")
        if pump_on is not None:
            sim.pump_on = bool(pump_on)
        else:
            sim.pump_on = not sim.pump_on
    except (SimulatorError, Exception):
        sim.pump_on = not sim.pump_on

    if sim.pump_on:
        sim._pump_start_grace_ticks = 5
    else:
        if sim.sim_faults.get("pump"):
            from apps.sensors.simulation.controls import clear_fault
            try:
                clear_fault(building_id, "pump")
            except Exception:
                logger.warning("Could not auto-clear pump fault on power-off (building=%s)", building_id)

    return json_ok({"pump_on": sim.pump_on, "elevator_on": sim.elevator_on, "faults": dict(sim.sim_faults)})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_toggle_elevator(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        elevator_on = body.get("on")
        if elevator_on is not None:
            sim.elevator_on = bool(elevator_on)
        else:
            sim.elevator_on = not sim.elevator_on
    except (SimulatorError, Exception):
        sim.elevator_on = not sim.elevator_on

    if not sim.elevator_on:
        # ── FIX-1 (BRECHA-1): Clear elevator faults when elevator is powered off.
        if sim.sim_faults.get("elevator"):
            from apps.sensors.simulation.controls import clear_fault
            try:
                clear_fault(building_id, "elevator")
            except Exception:
                logger.warning("Could not auto-clear elevator fault on power-off (building=%s)", building_id)

    return json_ok({"pump_on": sim.pump_on, "elevator_on": sim.elevator_on, "faults": dict(sim.sim_faults)})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_toggle_protection(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error("No hay simulador activo para este edificio", 404)

    sim.protection_on = not sim.protection_on
    if not sim.protection_on:
        sim._protection_grace_ticks_pump = 0
        sim._protection_grace_ticks_elev = 0

    return json_ok({"protection_on": sim.protection_on})

@require_http_methods(["POST"])
@login_required
@admin_required
def sim_toggle_auto_faults(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        enabled = body.get("enabled")
        if enabled is not None:
            sim.auto_faults_enabled = bool(enabled)
        else:
            sim.auto_faults_enabled = not getattr(sim, 'auto_faults_enabled', False)
    except (SimulatorError, Exception):
        sim.auto_faults_enabled = not getattr(sim, 'auto_faults_enabled', False)

    # Reset ticks when enabled
    if sim.auto_faults_enabled:
        sim._auto_fault_ticks = 0.0

    return json_ok({"auto_faults_enabled": sim.auto_faults_enabled})

