import json
from typing import Any, Dict, Optional

from django.db.models import Q, QuerySet

from apps.sensors.sensor_config import (
    VAR_NAMES, UNITS, VALUE_DISPLAY_ES, FAULT_NAMES_ES,
    RISK_NORMAL, RISK_CRITICO, RISK_ALTO, RISK_INFORMATIVO,
)
from apps.history.models import History


_RISK_ICONS = {
    RISK_NORMAL:      "fa-circle-check",
    RISK_CRITICO:     "fa-circle-exclamation",
    RISK_ALTO:        "fa-circle-exclamation",
    RISK_INFORMATIVO: "fa-circle-info",
}

_RISK_CSS = {
    RISK_NORMAL:      "risk-normal",
    RISK_CRITICO:     "risk-crit",
    RISK_ALTO:        "risk-high",
    RISK_INFORMATIVO: "risk-info",
}


def _build_severity_q(severity: str) -> Q:
    return (
        Q(**{"message__risk": severity})
        | Q(**{"message__contains": f'"risk": "{severity}"'})
        | Q(**{"message__contains": f'"risk":"{severity}"'})
    )


def filter_severity_include(queryset: QuerySet, severity: str) -> QuerySet:
    if not severity:
        return queryset
    return queryset.filter(_build_severity_q(severity))


def _build_history_query(
    user_id: int,
    role: str,
    building_id: Optional[str] = None,
) -> tuple[QuerySet, str]:
    from apps.core.auth_decorators import is_admin_role
    from apps.buildings.models import Building

    if is_admin_role(role):
        records = History.objects.all()
    else:
        records = History.objects.filter(
            Q(user_id=user_id)
            | Q(monitoring_equipment__building__user_assignments__user_id=user_id)
        ).distinct()

    if building_id:
        records = records.filter(monitoring_equipment__building_id=building_id)

    building_obj = Building.objects.filter(id=building_id).first() if building_id else None
    building_name = building_obj.name if building_obj else ""
    return records, building_name


def _make_parsed(
    risk: str, variable: str, value: object, action: str
) -> Dict[str, Any]:
    var_display = VAR_NAMES.get(variable, variable.replace("_", " ").title())

    if value is None:
        raw_str = ""
    else:
        raw_str = str(value).strip()

    value_str = raw_str.lower()

    if variable in VALUE_DISPLAY_ES:
        value_display = VALUE_DISPLAY_ES[variable].get(value_str, raw_str.capitalize())
        if value_str in ("true", "false") and variable in ("motor_stuck",):
            value_display = ""
    elif variable.startswith("fault_resolved_"):
        value_display = FAULT_NAMES_ES.get(value_str, raw_str.capitalize())
    elif raw_str:
        value_display = raw_str
    else:
        value_display = ""

    return {
        "parsed": True,
        "risk": risk,
        "variable": var_display,
        "value": value_display,
        "unit": UNITS.get(variable, ""),
        "action": action,
        "risk_icon": _RISK_ICONS.get(risk, "fa-circle-check"),
        "risk_css": _RISK_CSS.get(risk, "risk-info"),
    }


def parse_history_record_for_display(record: History) -> History:
    raw_msg = record.message

    if isinstance(raw_msg, str) and raw_msg.strip().startswith("{"):
        try:
            raw_msg = json.loads(raw_msg.strip())
        except (ValueError, KeyError):
            record.parsed_data = {"parsed": False}
            return record

    if isinstance(raw_msg, dict):
        record.parsed_data = _make_parsed(
            risk=raw_msg.get("risk", ""),
            variable=raw_msg.get("variable", ""),
            value=raw_msg.get("value"),
            action=raw_msg.get("action", ""),
        )
    else:
        record.parsed_data = {"parsed": False}

    return record
