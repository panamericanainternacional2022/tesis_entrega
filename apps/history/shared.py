import datetime as dt
import json
from typing import Any, Dict, Optional

from django.db.models import Q, QuerySet
from django.utils import timezone as tz

from apps.sensors.sensor_config import (
    VAR_NAMES, UNITS, VALUE_DISPLAY_ES, FAULT_NAMES_ES,
    RISK_NORMAL, RISK_CRITICO, RISK_ALTO, SEVERITY_LEVELS,
)
from apps.history.models import History, UserDismissedHistory


_RISK_ICONS = {
    RISK_NORMAL:      "fa-circle-check",
    RISK_CRITICO:     "fa-circle-exclamation",
    RISK_ALTO:        "fa-triangle-exclamation",
}

_RISK_CSS = {
    RISK_NORMAL:      "risk-normal",
    RISK_CRITICO:     "risk-crit",
    RISK_ALTO:        "risk-high",
}



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

    dismissed_ids = UserDismissedHistory.objects.filter(
        user_id=user_id
    ).values("history_record_id")
    records = records.exclude(id__in=dismissed_ids)

    if building_id:
        # FIX-HISTORY: Usar Q con OR para incluir registros guardados sin
        # MonitoringEquipment (monitoring_equipment=NULL). El filtro anterior
        # hacía INNER JOIN implícito y excluía esos registros silenciosamente.
        records = records.filter(
            Q(monitoring_equipment__building_id=building_id)
            | Q(monitoring_equipment__isnull=True)
        )

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
        "risk_css": _RISK_CSS.get(risk, "risk-normal"),
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
        fault_type = getattr(record, "fault_type", None) or raw_msg.get("fault_name")
        if fault_type and raw_msg.get("variables_detail"):
            fault_name = FAULT_NAMES_ES.get(fault_type, fault_type)
            var_details = raw_msg.get("variables_detail", [])
            var_names = [v.get("display_name", v.get("variable", "")) for v in var_details]
            variables_display = ", ".join(var_names) if var_names else ""
            value_display = f"{len(var_details)} sensores afectados"

            record.parsed_data = {
                "parsed": True,
                "risk": raw_msg.get("risk", ""),
                "variable": fault_name,
                "value": value_display,
                "unit": "",
                "action": raw_msg.get("action", ""),
                "risk_icon": _RISK_ICONS.get(raw_msg.get("risk", ""), "fa-circle-check"),
                "risk_css": _RISK_CSS.get(raw_msg.get("risk", ""), "risk-normal"),
                "is_compound": True,
                "fault_type": fault_type,
                "fault_name": fault_name,
                "variables_detail": var_details,
                "variables_display": variables_display,
            }
        else:
            record.parsed_data = _make_parsed(
                risk=raw_msg.get("risk", ""),
                variable=raw_msg.get("variable", ""),
                value=raw_msg.get("value"),
                action=raw_msg.get("action", ""),
            )
        if getattr(record, "resolved", False):
            record.parsed_data["risk"] = "Resuelta"
            record.parsed_data["risk_icon"] = "fa-check"
            record.parsed_data["risk_css"] = "risk-resolved"
    else:
        record.parsed_data = {"parsed": False}

    return record


def filter_date_range(queryset: QuerySet, period: str, date_from: str, date_to: str) -> QuerySet:
    if period == "custom":
        if date_from:
            try:
                naive = dt.datetime.strptime(date_from, "%Y-%m-%d")
                queryset = queryset.filter(date__gte=tz.make_aware(naive))
            except ValueError:
                pass
        if date_to:
            try:
                naive = dt.datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                queryset = queryset.filter(date__lte=tz.make_aware(naive))
            except ValueError:
                pass
    return queryset


def build_query_string(**params: str) -> str:
    return "&".join(f"{k}={v}" for k, v in params.items() if v)


def parse_history(records: QuerySet) -> list:
    parsed = []
    for record in records:
        parsed.append(parse_history_record_for_display(record))
    return parsed


def extract_variables(parsed_list: list) -> list[str]:
    return sorted({
        n.parsed_data["variable"]
        for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("variable")
    })


def extract_severities(parsed_list: list) -> list[str]:
    present = {
        n.parsed_data["risk"]
        for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("risk")
    }
    result = [s for s in SEVERITY_LEVELS if s in present]
    if "Resuelta" in present:
        result.append("Resuelta")
    return result


def filter_severity_python(parsed_list: list, severity: str) -> list:
    if not severity:
        return parsed_list
    return [
        n for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("risk") == severity
    ]


def filter_by_variable(parsed_list: list, variable: str) -> list:
    if not variable:
        return parsed_list
    return [
        n for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("variable") == variable
    ]
