import logging
import math
import time as time_module

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required, admin_required
from apps.sensors.simulation.exceptions import SimulatorError
from .shared import get_simulator, get_first_simulator, json_error_response, json_success_response, parse_json_body


logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
@login_required
@admin_required
def manual_update(request) -> JsonResponse:
    from apps.sensors.sensor_config import PUMP_VARS, RISK_CRITICO, RISK_ALTO, RISK_NORMAL, BOOLEAN_VARS, ENUM_VARS
    from apps.sensors.simulation.constants import MAX_HISTORY_SIZE
    try:
        body = parse_json_body(request)
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)

    variable = body.get("variable")
    value = body.get("value")
    building_id = body.get("edificio_id")

    sim = None
    if building_id:
        try:
            sim = get_simulator(building_id)
        except SimulatorError:
            pass
    if not sim:
        sim = get_first_simulator()
    if not sim:
        return json_error_response("No hay simuladores activos", 404)

    if variable not in sim.sensor_data:
        return json_error_response("Variable no válida")

    if variable in ENUM_VARS:
        if variable == "door_status":
            if value not in ("open", "closed"):
                return json_error_response('door_status debe ser "open" o "closed"')
            parsed_value = str(value)
    elif variable in BOOLEAN_VARS:
        if isinstance(value, str) and value.lower() == "false":
            parsed_value = False
        else:
            parsed_value = bool(value)
    else:
        try:
            parsed_value = float(value)
            if math.isnan(parsed_value) or math.isinf(parsed_value):
                return json_error_response("Valor numérico inválido (NaN o Infinito)")
        except (ValueError, TypeError):
            return json_error_response("Valor numérico inválido")

    import time
    if not hasattr(sim, "manual_overrides") or not isinstance(sim.manual_overrides, dict):
        sim.manual_overrides = {}
    if not hasattr(sim, "manual_targets") or not isinstance(sim.manual_targets, dict):
        sim.manual_targets = {}

    if variable == "position":
        # Posición manual es una solicitud de viaje del elevador, no bloquea el sensor
        sim._elev_target_floor = int(parsed_value)
        floor_num = round(sim.sensor_data.get("position", 0.0))
        sim._elev_direction = 1 if sim._elev_target_floor > floor_num else -1
        if sim._elev_state in ("IDLE", "DOORS_OPEN"):
            sim._elev_state = "DOOR_CLOSING"
            sim._elev_timer = 0.0
    elif variable == "speed":
        sim.manual_overrides["speed"] = time.time() + 90.0
        sim.manual_targets["speed"] = parsed_value
        position = body.get("position")
        if position is not None:
            sim._elev_target_floor = int(position)
            floor_num = round(sim.sensor_data.get("position", 0.0))
            sim._elev_direction = 1 if sim._elev_target_floor > floor_num else -1
            if sim._elev_state in ("IDLE", "DOORS_OPEN"):
                sim._elev_state = "DOOR_CLOSING"
                sim._elev_timer = 0.0
    elif variable == "motor_stuck":
        if parsed_value:
            sim.manual_overrides["motor_stuck"] = time.time() + 90.0
            sim.manual_targets["motor_stuck"] = True
            sim.manual_overrides["speed"] = time.time() + 90.0
            sim.manual_targets["speed"] = 0.0
            sim.manual_overrides["energy"] = time.time() + 90.0
            sim.manual_targets["energy"] = 15.0
        else:
            sim.sensor_data["motor_stuck"] = False
            for k in ("motor_stuck", "speed", "energy"):
                sim.manual_overrides.pop(k, None)
                sim.manual_targets.pop(k, None)
    else:
        sim.manual_overrides[variable] = time.time() + 90.0
        sim.manual_targets[variable] = parsed_value

    from apps.core.services.risk_service import classify_risk
    from apps.thresholds.services import get_thresholds

    thresholds = get_thresholds(sim.edificio_id)
    if variable in BOOLEAN_VARS:
        risk = RISK_CRITICO if parsed_value else RISK_NORMAL
    else:
        risk, _ = classify_risk(
            variable, parsed_value, thresholds,
            pump_on=sim.pump_on,
            speed=sim.sensor_data.get("speed", 0.0),
            door_close_attempts=sim.door_close_attempts
        )

    timestamp = time_module.strftime("%Y-%m-%d %H:%M:%S")
    sensor_type = "Bomba" if variable in PUMP_VARS else "Elevador"
    sim.history.append({
        "timestamp": timestamp,
        "type": sensor_type,
        "variable": variable,
        "value": parsed_value,
        "risk": risk,
        "color": "red" if risk in (RISK_ALTO, RISK_CRITICO) else "green",
    })
    if len(sim.history) > MAX_HISTORY_SIZE:
        sim.history = sim.history[-MAX_HISTORY_SIZE:]

    return json_success_response({"variable": variable, "value": parsed_value, "risk": risk})


@login_required
def sim_status(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

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
    })


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_pause(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

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
        sim.pump_on = sim.has_pump
        sim.elevator_on = sim.has_elevator
        if sim.has_pump:
            sim._pump_start_grace_ticks = 10

    return json_success_response({"paused": sim.sim_paused, "started": sim.sim_started})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_reset(request, building_id: int) -> JsonResponse:
    from apps.sensors.simulation.controls import reset_simulator

    try:
        message = reset_simulator(building_id)
        return json_success_response({"message": message})
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_inject_fault(request, building_id: int) -> JsonResponse:
    try:
        body = parse_json_body(request)
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)

    device = body.get("device")
    fault_type = body.get("fault_type")
    if not device or not fault_type:
        return json_error_response("Faltan campos: device, fault_type")

    from apps.sensors.simulation.controls import inject_fault

    try:
        message = inject_fault(building_id, device, fault_type)
        return json_success_response({"message": message})
    except SimulatorError as e:
        return json_error_response(e.message)


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_clear_fault(request, building_id: int) -> JsonResponse:
    try:
        body = parse_json_body(request)
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)

    device = body.get("device")

    from apps.sensors.simulation.controls import clear_fault

    try:
        message = clear_fault(building_id, device)
        return json_success_response({"message": message})
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_set_speed(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        speed = float(body.get("speed", 1.0))
        if math.isnan(speed) or math.isinf(speed):
            return json_error_response("Velocidad inválida (NaN o Infinito)")
    except (SimulatorError, ValueError, TypeError):
        return json_error_response("JSON inválido o speed no numérico")

    from apps.sensors.simulation.constants import MIN_SIM_SPEED, MAX_SIM_SPEED
    sim.sim_speed = max(MIN_SIM_SPEED, min(MAX_SIM_SPEED, speed))
    return json_success_response({"speed": sim.sim_speed})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_toggle_pump(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

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
        sim.manual_pump_override = False
        sim._pump_start_grace_ticks = 5
    else:
        sim.manual_pump_override = True

    return json_success_response({"pump_on": sim.pump_on})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_toggle_elevator(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        elevator_on = body.get("on")
        if elevator_on is not None:
            sim.elevator_on = bool(elevator_on)
        else:
            sim.elevator_on = not sim.elevator_on
    except (SimulatorError, Exception):
        sim.elevator_on = not sim.elevator_on

    if sim.elevator_on:
        sim.manual_elevator_override = False
    else:
        sim.manual_elevator_override = True

    return json_success_response({"elevator_on": sim.elevator_on})
