import json

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods

from apps.buildings.models import Building
from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_request import get_building_id_param
from apps.core.services.http_response import json_error, json_ok
from apps.dashboard.shared import build_monitoring_config
from apps.limits.services import get_sensor_limits, bulk_update_limits, LimitPersistenceError
from apps.sensors.sensor_config import SENSOR_RANGES
from apps.thresholds.services import get_thresholds


@login_required
@admin_required
def render_admin_limits(request) -> HttpResponse:
    from apps.core.auth_decorators import is_admin_role
    rol = request.session.get("usuario_rol", "US")
    buildings = list(Building.objects.all())
    valid_ids = [b.pk for b in buildings]
    default_id = valid_ids[0] if valid_ids else 0

    building_id = get_building_id_param(request, "edificio", "edificio_id")
    try:
        building_id = int(building_id) if building_id else default_id
    except (ValueError, TypeError):
        building_id = default_id

    if building_id not in valid_ids:
        building_id = default_id

    return render(
        request,
        "limits/limits.html",
        {
            "rol": rol,
            "edificios": buildings,
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
            "is_admin": is_admin_role(rol),
        },
    )


@login_required
@require_http_methods(["GET"])
def view_get_sensor_limits(request: HttpRequest) -> JsonResponse:
    try:
        building_id = int(request.GET.get("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido", status=400)

    limits = get_sensor_limits(building_id)
    return json_ok({"limits": limits})


def _validate_limit_input(
    data: dict, thresholds: dict
) -> tuple[dict[str, float], dict[str, str]]:
    errors: dict[str, str] = {}
    cleaned: dict[str, float] = {}

    for variable, max_val_raw in data.items():
        raw = str(max_val_raw)
        raw_clean = raw.replace("-", "").replace(".", "")
        if len(raw_clean) > 10:
            errors[variable] = "Demasiados dígitos enteros. Máximo 10."
            continue
        if "." in raw and len(raw.split(".")[1]) > 4:
            errors[variable] = "Demasiados decimales. Máximo 4."
            continue

        try:
            max_val = float(max_val_raw)
        except (ValueError, TypeError):
            errors[variable] = "Value must be numeric"
            continue

        from apps.sensors.sensor_config import SENSOR_ABSOLUTE_RANGES
        abs_max = SENSOR_ABSOLUTE_RANGES.get(variable, (0.0, 999999.0))[1]
        if max_val > abs_max:
            errors[variable] = (
                f"El límite máximo no puede exceder el límite físico absoluto ({abs_max})"
            )
            continue

        default_min = SENSOR_RANGES.get(variable, (0.0, 100.0))[0]
        if max_val <= default_min:
            errors[variable] = (
                f"El límite máximo ({max_val}) debe ser mayor "
                f"que el mínimo por defecto ({default_min})"
            )
            continue

        if variable in thresholds:
            t_config = thresholds[variable]
            direction = t_config.get("direction")
            is_lower = direction == "lower"
            
            max_thresh_key = "high" if is_lower else "critic"
            
            if max_thresh_key in t_config:
                max_thresh = float(t_config[max_thresh_key])
                if max_val < max_thresh:
                    label = (
                        "alto" if is_lower
                        else "límite crítico superior" if direction == "range"
                        else "crítico"
                    )
                    errors[variable] = (
                        f"El límite máximo ({max_val}) no puede ser "
                        f"inferior al umbral {label} ({max_thresh})"
                    )

        cleaned[variable] = max_val

    return cleaned, errors


@require_http_methods(["POST"])
@login_required
@admin_required
def view_update_sensor_limits(request: HttpRequest) -> JsonResponse:
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

    thresholds = get_thresholds(building_id)
    cleaned_data, errors = _validate_limit_input(raw, thresholds)

    if errors:
        return json_error(f"Validation errors: {errors}")

    try:
        bulk_update_limits(cleaned_data, building_id)
    except LimitPersistenceError as e:
        return json_error(str(e), status=500)

    return json_ok({
        "sensor_ranges": get_sensor_limits(building_id),
    })

