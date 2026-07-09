import json
import logging
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods

from apps.buildings.models import Building
from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_error, json_ok
from apps.dashboard.shared import build_monitoring_config
from apps.limits.services import get_sensor_limits
from apps.thresholds.services import get_thresholds, bulk_update, ThresholdPersistenceError

logger = logging.getLogger(__name__)
VALID_DIRECTIONS = frozenset({"higher", "lower", "range"})


@login_required
def render_admin_thresholds(request: HttpRequest) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    buildings = list(Building.objects.only("pk", "name", "floors"))

    from apps.core.services.http_request import get_building_id_param
    building_id = get_building_id_param(request, "edificio", "edificio_id")
    valid_ids = [b.pk for b in buildings]

    try:
        building_id = int(building_id) if building_id else 0
    except (ValueError, TypeError):
        building_id = 0
    if building_id not in valid_ids:
        building_id = valid_ids[0] if valid_ids else 0

    return render(
        request,
        "thresholds/thresholds.html",
        {
            "rol": rol,
            "edificios": buildings,
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
            "is_admin": True,
        },
    )


@login_required
@require_http_methods(["GET"])
def view_get_thresholds(request: HttpRequest) -> JsonResponse:
    try:
        building_id = int(request.GET.get("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido", status=400)
    return json_ok(get_thresholds(building_id))


def _validate_threshold_config(
    variable: str, config: dict, building_id: int
) -> str | None:
    if not isinstance(config, dict):
        return "Invalid config format"

    direction = config.get("direction")
    if direction not in VALID_DIRECTIONS:
        return f"Invalid direction: {direction}"

    try:
        low = float(config.get("low", 0))
        if direction == "range":
            if "high" not in config:
                return "Missing 'high' for range direction"
            high = float(config["high"])
        else:
            medium = float(config.get("medium", 0))
            high = float(config.get("high", 0))
    except (ValueError, TypeError) as e:
        logger.warning(
            "Threshold non-numeric for %s: %s — config=%s", variable, e, config
        )
        return f"Non-numeric threshold value: config={config}"

    if direction == "range":
        if low >= high:
            logger.warning(
                "Threshold range fail for %s: low=%s high=%s", variable, low, high
            )
            return f"Low limit ({low}) must be lower than high limit ({high})"
    elif direction == "higher":
        if not (low < medium < high):
            logger.warning(
                "Threshold higher fail for %s: low=%s med=%s high=%s",
                variable, low, medium, high,
            )
            return (
                f"Thresholds must be ascending: "
                f"low={low} < medium={medium} < high={high}"
            )
    elif direction == "lower":
        if not (low > medium > high):
            return "Thresholds must be descending: low > medium > high"

    sensor_limits = get_sensor_limits(building_id)
    limits = sensor_limits.get(variable)
    if limits:
        min_bound, max_bound = limits
        if direction == "range":
            if low < min_bound or high > max_bound:
                return (
                    f"Los umbrales [{low}, {high}] deben estar dentro de "
                    f"los límites físicos del sensor [{min_bound}, {max_bound}]"
                )
        elif direction == "higher":
            if low < min_bound or high > max_bound:
                return (
                    f"Los umbrales deben estar dentro de los límites físicos "
                    f"del sensor [{min_bound}, {max_bound}] "
                    f"(recibido low={low}, high={high})"
                )
        elif direction == "lower":
            if low > max_bound or high < min_bound:
                return (
                    f"Los umbrales deben estar dentro de los límites físicos "
                    f"del sensor [{min_bound}, {max_bound}] "
                    f"(recibido low={low}, high={high})"
                )

    config["low"] = low
    config["high"] = high
    if direction != "range":
        config["medium"] = medium
    return None


@require_http_methods(["POST"])
@login_required
@admin_required
def view_update_thresholds(request: HttpRequest) -> JsonResponse:
    try:
        raw = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    if not isinstance(raw, dict):
        return json_error("Body must be a JSON object")

    try:
        building_id = int(raw.pop("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido")

    errors: dict[str, str] = {}
    for variable, config in raw.items():
        error = _validate_threshold_config(variable, config, building_id)
        if error:
            errors[variable] = error

    if errors:
        return json_error(f"Validation errors: {errors}")

    try:
        bulk_update(raw, building_id)
    except ThresholdPersistenceError as e:
        return json_error(str(e), status=500)

    return json_ok({"thresholds": get_thresholds(building_id)})
