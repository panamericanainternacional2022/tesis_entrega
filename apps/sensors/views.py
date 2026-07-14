import logging
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Avg, Min, Max
from django.views.decorators.http import require_GET

from apps.core.auth_decorators import login_required
from apps.sensors.models import SensorReading
from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS

logger = logging.getLogger(__name__)


@require_GET
@login_required
def daily_summary(request, building_id: int) -> JsonResponse:
    days = min(int(request.GET.get("days", 7)), 30)
    cutoff = timezone.now() - timedelta(days=days)

    readings = (
        SensorReading.objects.filter(building_id=building_id, timestamp__gte=cutoff)
        .extra(select={"day": "DATE(fecha)"})
        .values("variable", "day")
        .annotate(avg=Avg("value"), min=Min("value"), max=Max("value"))
        .order_by("day")
    )

    variables = set()
    by_day: dict[str, dict] = {}
    for row in readings:
        var = row["variable"]
        day = str(row["day"])
        variables.add(var)
        by_day.setdefault(day, {})[var] = {
            "avg": round(row["avg"], 4),
            "min": round(row["min"], 4),
            "max": round(row["max"], 4),
        }

    labels = sorted(by_day.keys())
    pump_vars = [v for v in PUMP_VARS if v in variables]
    elev_vars = [v for v in ELEVATOR_VARS if v in variables]

    def _build_group(vars_list):
        result = {}
        for v in vars_list:
            result[v] = {
                "avg": [by_day[d].get(v, {}).get("avg") for d in labels],
                "min": [by_day[d].get(v, {}).get("min") for d in labels],
                "max": [by_day[d].get(v, {}).get("max") for d in labels],
            }
        return result

    return JsonResponse({
        "labels": labels,
        "pump": _build_group(pump_vars),
        "elevator": _build_group(elev_vars),
    })
