from django.shortcuts import render
from django.http import HttpResponse, HttpRequest

from apps.core.auth_decorators import login_required, is_admin_role
from apps.core.services.http_request import get_building_id_param
from apps.buildings.models import Building

from .shared import build_monitoring_config, get_user_building_ids
from apps.sensors.sensor_config import PUMP_FAULT_KEYS, ELEVATOR_FAULT_KEYS, FAULT_NAMES_ES


@login_required
def monitoring_view(request: HttpRequest) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    user_id = request.session.get("usuario_id")

    if is_admin_role(rol):
        buildings = list(Building.objects.all())
    else:
        user_building_ids = get_user_building_ids(user_id)
        buildings = list(Building.objects.filter(pk__in=user_building_ids))

    building_id_raw = get_building_id_param(request, "edificio", "edificio_id")
    valid_ids = [b.pk for b in buildings]
    if building_id_raw:
        try:
            building_id = int(building_id_raw)
            if building_id not in valid_ids:
                building_id = valid_ids[0] if valid_ids else 0
        except (ValueError, TypeError):
            building_id = valid_ids[0] if valid_ids else 0
    else:
        building_id = valid_ids[0] if valid_ids else 0

    return render(
        request,
        "dashboard/monitoring_dashboard.html",
        {
            "edificios": buildings,
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
            "is_admin": is_admin_role(rol),
            "PUMP_FAULT_OPTIONS": [(k, FAULT_NAMES_ES[k]) for k in PUMP_FAULT_KEYS],
            "ELEVATOR_FAULT_OPTIONS": [(k, FAULT_NAMES_ES[k]) for k in ELEVATOR_FAULT_KEYS],
        },
    )
