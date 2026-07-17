import json
import logging
from typing import Any, Dict, List, Optional

from apps.history.models import History
from apps.sensors.sensor_config import RISK_CRITICO

logger = logging.getLogger(__name__)


def get_alert_log(edificio_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, str]]:
    try:
        qs = History.objects.select_related("monitoring_equipment__building")
        if edificio_id:
            qs = qs.filter(monitoring_equipment__building_id=edificio_id)
        entries: List[Dict[str, str]] = []
        for n in qs.order_by("-date")[:limit]:
            try:
                raw = n.message
                if isinstance(raw, str):
                    data = json.loads(raw)
                else:
                    data = raw

                entry = {
                    "timestamp": n.date.strftime("%Y-%m-%d %H:%M:%S"),
                    "variable": data.get("variable", ""),
                    "value": data.get("value", ""),
                    "risk": data.get("risk", ""),
                    "message": data.get("action", ""),
                }

                if n.fault_type:
                    entry["fault_type"] = n.fault_type
                    entry["fault_name"] = data.get("fault_name", n.fault_type)
                    entry["variables"] = n.affected_variables or []
                    entry["variables_detail"] = data.get("variables_detail", [])

                entries.append(entry)
            except (json.JSONDecodeError, AttributeError):
                entries.append({
                    "timestamp": n.date.strftime("%Y-%m-%d %H:%M:%S") if n.date else "",
                    "variable": "",
                    "value": "",
                    "risk": "",
                    "message": str(n.message or ""),
                })
        return entries
    except Exception as e:
        logger.warning("Could not retrieve alert_log from DB: %s", e)
        return []


def save_compound_history_record(
    fault_type: str,
    affected_vars: dict,
    risk_level: str,
    recommended_action: str,
    edificio_id: Optional[int] = None,
) -> None:
    try:
        from django.utils import timezone
        from apps.sensors.sensor_config import FAULT_NAMES_ES, VAR_NAMES, UNITS

        equipo, usuario = _find_equipment_by_fault(fault_type, edificio_id)
        if not usuario:
            return

        fault_name = FAULT_NAMES_ES.get(fault_type, fault_type)
        var_summaries = []
        for var, info in affected_vars.items():
            display = VAR_NAMES.get(var, var)
            unit = UNITS.get(var, "")
            value = info.get("value", "N/A")
            var_risk = info.get("risk", risk_level)
            var_summaries.append({
                "variable": var,
                "display_name": display,
                "value": str(value) if value is not None else None,
                "unit": unit,
                "risk": var_risk,
            })

        worst_value = None
        for var, info in affected_vars.items():
            if info.get("risk") == RISK_CRITICO:
                worst_value = info.get("value")
                break
        if worst_value is None and affected_vars:
            worst_value = next(iter(affected_vars.values())).get("value")

        mensaje_data: Dict[str, Any] = {
            "risk": risk_level,
            "variable": fault_type,
            "value": str(worst_value) if worst_value is not None else None,
            "action": recommended_action,
            "fault_name": fault_name,
            "variables_detail": var_summaries,
        }
        History.objects.create(
            user=usuario,
            monitoring_equipment=equipo,
            date=timezone.now(),
            message=mensaje_data,
            fault_type=fault_type,
            affected_variables=[v["variable"] for v in var_summaries],
        )
    except Exception as e:
        # FIX-11 (BRECHA-11): Upgrade to error so compound data-loss is visible
        logger.error(
            "LOSS: Could not save compound history record in Django DB — "
            "fault_type=%s risk=%s error=%s",
            fault_type, risk_level, e,
        )


def _find_equipment_by_fault(fault_type: str, edificio_id: Optional[int]) -> Any:
    from apps.sensors.sensor_config import PUMP_FAULT_KEYS, ELEVATOR_FAULT_KEYS
    from apps.buildings.models import MonitoringEquipment
    from apps.users.models import Usuario
    from apps.core.auth_decorators import ADMIN_ROLES

    tipo = None
    if fault_type in PUMP_FAULT_KEYS:
        tipo = MonitoringEquipment.TYPE_PUMP
    elif fault_type in ELEVATOR_FAULT_KEYS:
        tipo = MonitoringEquipment.TYPE_ELEVATOR

    equipo = (
        MonitoringEquipment.objects.filter(building_id=edificio_id, equipment_type=tipo).first()
        if tipo and edificio_id else None
    ) or (
        MonitoringEquipment.objects.filter(building_id=edificio_id).first()
        if edificio_id else None
    )

    usuario = Usuario.objects.filter(rol__in=ADMIN_ROLES).first() or Usuario.objects.first()
    return equipo, usuario
