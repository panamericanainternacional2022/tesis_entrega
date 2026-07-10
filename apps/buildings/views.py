import datetime as _dt_bld
import logging as _logging_bld
from typing import Any

from django.contrib import messages
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_ok
from apps.buildings.models import Building, MonitoringEquipment
from apps.buildings.services import (
    sync_equipment_for_building, EquipmentConfig,
)
from apps.buildings.validators import validate_building_form, validate_unique_rif
from apps.users.validators import normalize_rif
from apps.buildings.shared import (
    extract_building_data,
    extract_equipment_config,
)
from apps.sensors.sensor_config import (
    RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
    SEVERITY_LEVELS, SEVERITY_DISPLAY_LEVELS, RISK_STYLES,
    PUMP_VARS, ELEVATOR_VARS, RATIONING_THRESHOLD, SENSOR_RANGES,
    VAR_NAMES, UNITS, STATS_VARS, ACTIONS, VALUE_DISPLAY_ES,
)
from apps.history.models import History
from apps.core.services.risk_service import classify_risk
from apps.thresholds.services import get_thresholds
from apps.sensors.simulation.globals import simulators
from apps.core.services.pdf_shared import _pdf_font, draw_row, safe_text
from apps.core.services.pdf_rendering import (
    _create_report_pdf,
    render_pdf_header, render_section_divider, render_summary_box,
    render_severity_legend, render_text_progress_bar, render_table_header,
)


def _validate_floors_elevator(floors: str, has_elevator: bool) -> str | None:
    try:
        floors_val = int(floors)
        if has_elevator and floors_val <= 1:
            return "Un edificio de 1 piso no puede tener elevador."
    except (ValueError, TypeError):
        return "La cantidad de pisos debe ser un número entero."
    return None


@login_required
@admin_required
def building_list_view(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    equipamiento = request.GET.get("equipamiento", "").strip()

    buildings = Building.objects.all().prefetch_related("equipment")

    if equipamiento == "elevador":
        buildings = buildings.filter(equipment__equipment_type="elevador")

    if query:
        buildings = buildings.filter(
            Q(name__icontains=query)
            | Q(rif__icontains=query)
        )

    buildings = buildings.distinct()
    return render(
        request,
        "buildings/building_list.html",
        {
            "buildings": list(buildings),
            "page_messages": [],
            "current_equipamiento": equipamiento,
        },
    )


@login_required
@admin_required
def register_building_view(request: HttpRequest) -> HttpResponse:
    building_data = {}
    form_errors = {}
    config = EquipmentConfig()

    if request.method == "POST":
        data = extract_building_data(request)
        if data.get("rif"):
            data["rif"] = normalize_rif(data["rif"])
        building_data = data
        config = extract_equipment_config(request)

        form_errors = validate_building_form({
            "nombreEdificio": data["name"],
            "direccion": data["address"],
            "rif": data["rif"],
            "cantidadPisos": data.get("floors"),
        })
        if not form_errors:
            error = _validate_floors_elevator(data.get("floors"), config.has_elevator)
            if error:
                form_errors["cantidadPisos"] = error
        if form_errors:
            messages.error(request, "Corrija los errores indicados en el formulario.")
        else:
            with transaction.atomic():
                building = Building.objects.create(
                    name=data["name"], rif=data["rif"], address=data["address"],
                    floors=int(data["floors"]),
                )
                sync_equipment_for_building(building, config)
            messages.success(request, "Edificio registrado correctamente.")
            return redirect("building_list")

    return render(
        request,
        "buildings/building_register.html",
        {
            "editing": False,
            "form_errors": form_errors,
            "building": building_data,
            "has_elevator": config.has_elevator,
        },
    )


@login_required
@admin_required
def edit_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    form_errors = {}

    equipment_types = set(building.equipment.values_list("equipment_type", flat=True))
    has_elevator = MonitoringEquipment.TYPE_ELEVATOR in equipment_types

    if request.method == "POST":
        data = extract_building_data(request)
        if data.get("rif"):
            data["rif"] = normalize_rif(data["rif"])

        has_elevator = request.POST.get("con_elevador") == "true"
        config = EquipmentConfig(has_elevator=has_elevator)

        form_errors = validate_building_form(
            {
                "nombreEdificio": data["name"],
                "direccion": data["address"],
                "rif": data["rif"],
                "cantidadPisos": data.get("floors"),
            },
            exclude_building_id=building.id,
        )
        if not form_errors:
            error = _validate_floors_elevator(data.get("floors"), config.has_elevator)
            if error:
                form_errors["cantidadPisos"] = error
        if form_errors:
            messages.error(request, "Corrija los errores indicados en el formulario.")
        else:
            with transaction.atomic():
                building.name = data["name"]
                building.address = data["address"]
                building.rif = data["rif"]
                building.floors = int(data["floors"])
                building.save()
                sync_equipment_for_building(building, config)
            messages.success(request, "Edificio actualizado correctamente.")
            return redirect("building_list")

    return render(
        request,
        "buildings/building_register.html",
        {
            "editing": True,
            "building": building,
            "form_errors": form_errors,
            "has_elevator": has_elevator,
        },
    )


@login_required
@admin_required
def delete_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    building.delete()
    messages.success(
        request,
        "El edificio y todos sus datos asociados se eliminaron correctamente.",
    )
    return redirect("building_list")


def check_rif_uniqueness_view(request: HttpRequest) -> JsonResponse:
    rif = request.GET.get("rif", "").strip()
    exclude_id = request.GET.get("exclude_id", "").strip()
    exclude_building_id = int(exclude_id) if exclude_id.isdigit() else None

    if not rif:
        return json_ok({"exists": False})

    normalized = normalize_rif(rif)
    try:
        validate_unique_rif(normalized, exclude_building_id)
        exists = False
        error = ""
    except ValidationError as e:
        exists = True
        error = str(e)

    return json_ok({"exists": exists, "error": error})


_logger_bld = _logging_bld.getLogger(__name__)

_EQUIP_STATUS_STYLE: dict[str, tuple[tuple, tuple]] = {
    "activo":    ((240, 253, 244), (22, 101, 52)),
    "inactivo":  ((245, 245, 245), (107, 107, 107)),
    "fallo":     ((254, 242, 242), (220, 38, 38)),
    "pausado":   ((255, 247, 237), (194, 65, 12)),
}
_EQUIP_TYPE_ES: dict[str, str] = {
    "bomba":    "Bomba de agua",
    "elevador": "Elevador",
}


def generate_building_report_bytes(edificio_id: int, request: Any = None) -> tuple[bytes, str]:

    building = get_object_or_404(Building, id=edificio_id)
    pdf = _create_report_pdf("Reporte de estado del edificio")
    now = _dt_bld.datetime.now()
    sim = simulators.get(edificio_id)
    thresholds = get_thresholds(edificio_id)

    equipment = list(MonitoringEquipment.objects.filter(building_id=edificio_id))
    pump_status = None
    elevator_status = None
    equip_types = set()
    for eq in equipment:
        equip_types.add(eq.equipment_type)
        if eq.equipment_type == "bomba":
            pump_status = eq.status
        elif eq.equipment_type == "elevador":
            elevator_status = eq.status

    sensor_data = sim.sensor_data if sim else {}
    history = sim.history if sim else []
    stats = _compute_stats(history, STATS_VARS)

    pump_on = sim.pump_on if sim else False
    speed = sensor_data.get("speed", 0.0)
    door_close_attempts = sim.door_close_attempts if sim else 0

    relevant_vars = set()
    if "bomba" in equip_types:
        relevant_vars.update(PUMP_VARS)
    if "elevador" in equip_types:
        relevant_vars.update(ELEVATOR_VARS)

    address = building.address[:80] + ("..." if len(building.address) > 80 else "")

    render_pdf_header(
        pdf,
        title="Reporte de estado del edificio",
        now=now,
        meta_lines=[
            f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}",
            f"Edificio: {building.name}",
            f"RIF: {building.rif}",
            f"Dirección: {address}",
        ],
    )

    _render_executive_summary(
        pdf, sensor_data, thresholds, relevant_vars, pump_status, elevator_status, equip_types,
        pump_on=pump_on, speed=speed, door_close_attempts=door_close_attempts
    )
    _render_equipment_summary(pdf, equipment)
    render_severity_legend(pdf)

    critical_items = _get_critical_items(
        sensor_data, thresholds, relevant_vars,
        pump_on=pump_on, speed=speed, door_close_attempts=door_close_attempts
    )
    if critical_items:
        _render_critical_section(pdf, critical_items, VAR_NAMES, UNITS, ACTIONS, VALUE_DISPLAY_ES)

    _render_current_readings(
        pdf, sensor_data, thresholds, relevant_vars, equip_types, VAR_NAMES, UNITS, ACTIONS, VALUE_DISPLAY_ES,
        pump_on=pump_on, speed=speed, door_close_attempts=door_close_attempts
    )
    _render_rationing_section(pdf, sensor_data)

    if stats:
        _render_stats_table(pdf, stats, relevant_vars, VAR_NAMES, UNITS)

    usuario_id = request.session.get("usuario_id") if request else None
    usuario_rol = request.session.get("usuario_rol", "US") if request else "US"
    _render_history_section(pdf, edificio_id, usuario_id, usuario_rol)
    _render_thresholds(pdf, thresholds, relevant_vars, VAR_NAMES, UNITS)
    _render_limits_section(pdf, edificio_id, relevant_vars, VAR_NAMES, UNITS)

    filename = f"reporte_{building.name}_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")

    pdf_raw = pdf.output()
    pdf_bytes = pdf_raw.encode("utf-8") if isinstance(pdf_raw, str) else bytes(pdf_raw)
    return pdf_bytes, filename


@login_required
def building_report_pdf_view(request: Any, edificio_id: int) -> HttpResponse:
    try:
        pdf_bytes, filename = generate_building_report_bytes(edificio_id, request=request)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain", status=500,
        )
    except Exception as e:
        _logger_bld.warning("Building report PDF failed: %s", e)
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain", status=500,
        )


def _compute_stats(history: list, stats_vars: list) -> dict:
    stats = {}
    for var in stats_vars:
        vals = [
            r["value"]
            for r in history
            if r["variable"] == var
            and isinstance(r["value"], (int, float))
            and not isinstance(r["value"], bool)
        ]
        vals = vals[-500:]
        if vals:
            stats[var] = {
                "avg": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }
    return stats


def _get_critical_items(
    sensor_data: dict, thresholds: dict, relevant_vars: set,
    pump_on: bool = True, speed: float = 0.0, door_close_attempts: int = 0
) -> list[dict]:
    _CRITICAL_LEVELS = {RISK_ALTO, RISK_CRITICO}
    items = []
    for var in sorted(relevant_vars):
        if var not in sensor_data:
            continue
        risk, _ = classify_risk(
            var, sensor_data[var], thresholds,
            pump_on=pump_on, speed=speed, door_close_attempts=door_close_attempts
        )
        if risk in _CRITICAL_LEVELS:
            items.append({"var": var, "value": sensor_data[var], "risk": risk})
    return items


def _format_value(var: str, value, units: dict, value_display_map: dict = None) -> str:
    if value_display_map and var in value_display_map:
        val_str = str(value).lower()
        return value_display_map[var].get(val_str, str(value))
    if isinstance(value, bool):
        return "Sí" if value else "No"
    unit = units.get(var, "")
    display = f"{value:.1f}" if isinstance(value, float) else str(value)
    if unit:
        return f"{display} {unit}"
    return display


def _render_executive_summary(
    pdf: Any, sensor_data: dict, thresholds: dict,
    relevant_vars: set, pump_status, elevator_status,
    equip_types: set, pump_on: bool = True, speed: float = 0.0,
    door_close_attempts: int = 0
) -> None:

    render_section_divider(pdf, "Resumen ejecutivo")

    counts = {rl: 0 for rl in list(SEVERITY_LEVELS) + [RISK_NORMAL]}
    for var in relevant_vars:
        if var in sensor_data:
            risk, _ = classify_risk(
                var, sensor_data[var], thresholds,
                pump_on=pump_on, speed=speed, door_close_attempts=door_close_attempts
            )
            if risk in counts:
                counts[risk] += 1

    items = [
        {
            "label": risk,
            "value": f"{counts.get(risk, 0)} sensor(es)",
            "fill": fill,
            "text": text_c,
        }
        for risk, fill, text_c, _desc in SEVERITY_DISPLAY_LEVELS
    ]
    render_summary_box(pdf, items)

    _pdf_font(pdf, "", 10)
    pdf.set_text_color(26, 26, 26)
    if "bomba" in equip_types:
        status_str = pump_status.capitalize() if pump_status else "Desconocido"
        pdf.cell(0, 6, safe_text(f"Bomba de agua: {status_str}"), ln=1)
    if "elevador" in equip_types:
        status_str = elevator_status.capitalize() if elevator_status else "Desconocido"
        pdf.cell(0, 6, safe_text(f"Elevador: {status_str}"), ln=1)
    pdf.ln(4)


def _render_equipment_summary(
    pdf: Any,
    equipment: list,
) -> None:

    if not equipment:
        return

    render_section_divider(pdf, "Equipos registrados")

    col_widths = [80, 50, 60]
    col_headers = ["Nombre del equipo", "Tipo", "Estado"]
    col_aligns = ["L", "L", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    for idx, eq in enumerate(equipment):
        status_raw = (eq.status or "desconocido").lower()
        fill_c, text_c = _EQUIP_STATUS_STYLE.get(status_raw, ((249, 250, 251), (55, 65, 81)))
        type_label = _EQUIP_TYPE_ES.get(eq.equipment_type, eq.equipment_type.capitalize())
        status_label = status_raw.capitalize()

        draw_row(
            pdf, col_widths, col_aligns,
            [eq.name, type_label, status_label],
            [None, None, fill_c],
            [None, None, text_c],
            row_index=idx,
        )

    pdf.ln(4)


def _render_critical_section(
    pdf: Any, critical_items: list[dict],
    _VAR_NAMES: dict, _UNITS: dict, _ACTIONS: dict,
    _VALUE_DISPLAY_ES: dict = None,
) -> None:
    if pdf.get_y() > 240:
        pdf.add_page()

    render_section_divider(pdf, f"Sensores en estado {RISK_CRITICO} / {RISK_ALTO}")

    col_widths = [48, 26, 28, 88]
    col_headers = ["Variable", "Valor", "Severidad", "Acción recomendada"]
    col_aligns = ["L", "C", "C", "L"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    for idx, item in enumerate(critical_items):
        var = item["var"]
        val = item["value"]
        risk = item["risk"]
        val_str = _format_value(var, val, _UNITS, _VALUE_DISPLAY_ES)
        var_name = _VAR_NAMES.get(var, var)
        action = _ACTIONS.get(var, {}).get(risk, "")
        fill_c, text_c = RISK_STYLES.get(risk, ((255, 255, 255), (26, 26, 26)))

        draw_row(
            pdf, col_widths, col_aligns,
            [var_name, val_str, risk, action[:60]],
            [None, None, fill_c, None],
            [None, None, text_c, None],
            row_index=idx,
        )

    pdf.ln(6)


def _render_current_readings(
    pdf: Any, sensor_data: dict, thresholds: dict,
    relevant_vars: set, equip_types: set,
    _VAR_NAMES: dict, _UNITS: dict, _ACTIONS: dict,
    _VALUE_DISPLAY_ES: dict = None,
    pump_on: bool = True, speed: float = 0.0, door_close_attempts: int = 0
) -> None:
    if pdf.get_y() > 230:
        pdf.add_page()

    render_section_divider(pdf, "Lecturas actuales de sensores")

    col_widths = [48, 26, 28, 88]
    col_headers = ["Variable", "Valor", "Severidad", "Acción recomendada"]
    col_aligns = ["L", "C", "C", "L"]

    sections = []
    if "bomba" in equip_types:
        sections.append(("Bomba y Eléctricos", [v for v in PUMP_VARS if v in relevant_vars]))
    if "elevador" in equip_types:
        sections.append(("Elevador y Motor", [v for v in ELEVATOR_VARS if v in relevant_vars]))

    for section_name, vars_list in sections:
        if pdf.get_y() > 240:
            pdf.add_page()

        _pdf_font(pdf, "B", 10)
        pdf.set_text_color(55, 65, 81)
        pdf.cell(0, 7, safe_text(section_name), ln=1)
        pdf.ln(1)

        render_table_header(pdf, col_widths, col_aligns, col_headers)

        _pdf_font(pdf, "", 9)
        pdf.set_draw_color(10, 10, 10)
        row_idx = 0
        for var in vars_list:
            if var not in sensor_data:
                continue
            val = sensor_data[var]
            risk, _ = classify_risk(
                var, val, thresholds,
                pump_on=pump_on, speed=speed, door_close_attempts=door_close_attempts
            )
            val_str = _format_value(var, val, _UNITS, _VALUE_DISPLAY_ES)
            var_name = _VAR_NAMES.get(var, var)
            action = _ACTIONS.get(var, {}).get(risk, "")[:55]
            fill_c, text_c = RISK_STYLES.get(risk, ((255, 255, 255), (26, 26, 26)))

            draw_row(
                pdf, col_widths, col_aligns,
                [var_name, val_str, risk, action],
                [None, None, fill_c, None],
                [None, None, text_c, None],
                row_index=row_idx,
            )
            row_idx += 1

        pdf.ln(4)


def _render_rationing_section(pdf: Any, sensor_data: dict) -> None:
    if pdf.get_y() > 250:
        pdf.add_page()

    render_section_divider(pdf, "Estado general de racionamiento")

    flow = sensor_data.get("flow_rate")
    if flow is None:
        _pdf_font(pdf, "", 10)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(0, 7, safe_text("Sin datos de caudal disponibles."), ln=1)
        pdf.ln(4)
        return

    _flow_max = SENSOR_RANGES.get("flow_rate", (0, 60))[1]
    render_text_progress_bar(
        pdf,
        label=f"Caudal actual contra su límite actual ({RATIONING_THRESHOLD} l/s)",
        value=flow,
        max_value=_flow_max,
        threshold=RATIONING_THRESHOLD,
        unit="l/s",
    )

    in_rationing = flow < RATIONING_THRESHOLD
    if in_rationing:
        pdf.set_fill_color(254, 242, 242)
        pdf.set_text_color(220, 38, 38)
        label = "El racionamiento está activo, el caudal está por debajo del umbral de racionamiento."
    else:
        pdf.set_fill_color(240, 253, 244)
        pdf.set_text_color(22, 101, 52)
        label = "El caudal se encuentra dentro del rango aceptable."

    _pdf_font(pdf, "B", 10)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(0, 8, f"  {safe_text(label)}", 1, 1, "L", True)
    pdf.ln(4)


def _render_history_section(
    pdf: Any,
    edificio_id: int,
    usuario_id: int | None = None,
    usuario_rol: str = "US",
) -> None:
    from apps.history.shared import _build_history_query
    from apps.dashboard.shared import filter_date_range, parse_history

    if pdf.get_y() > 230:
        pdf.add_page()

    render_section_divider(pdf, "Historial en el período")

    if usuario_id:
        records, _ = _build_history_query(usuario_id, usuario_rol, str(edificio_id))
    else:
        records = History.objects.filter(
            monitoring_equipment__building_id=edificio_id,
        )

    records = filter_date_range(records, "24h", "", "")

    records = (
        records
        .select_related("monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )

    total = records.count()
    _pdf_font(pdf, "", 10)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(0, 7, safe_text(f"Últimas 24 horas: {total} registro(s)"), ln=1)
    pdf.ln(3)

    parsed = parse_history(records)
    counts: dict[str, int] = {}
    for n in parsed:
        risk = n.parsed_data.get("risk", "") if hasattr(n, "parsed_data") else ""
        if not risk:
            msg = n.message
            risk = msg.get("risk", "") if isinstance(msg, dict) else ""
        if risk:
            counts[risk] = counts.get(risk, 0) + 1

    if not counts:
        pdf.set_text_color(95, 95, 95)
        _pdf_font(pdf, "", 10)
        pdf.cell(0, 7, safe_text("No se registraron eventos en las últimas 24 horas."), ln=1)
        pdf.ln(4)
        return

    col_widths = [140, 50]
    col_headers = ["Severidad", "Cantidad"]
    col_aligns = ["L", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    row_idx = 0
    for risk_lvl, fill, text_c, _desc in SEVERITY_DISPLAY_LEVELS:
        cnt = counts.get(risk_lvl, 0)
        if cnt == 0:
            continue
        draw_row(
            pdf, col_widths, col_aligns,
            [risk_lvl, str(cnt)],
            [fill, None],
            [text_c, None],
            row_index=row_idx,
        )
        row_idx += 1

    pdf.ln(6)


def _render_stats_table(
    pdf: Any, stats: dict, relevant_vars: set,
    _VAR_NAMES: dict, _UNITS: dict,
) -> None:
    if pdf.get_y() > 230:
        pdf.add_page()

    render_section_divider(pdf, "Estadísticas última hora (promedio, mínimo, máximo)")

    col_widths = [82, 36, 36, 36]
    col_headers = ["Variable", "Promedio", "Mínimo", "Máximo"]
    col_aligns = ["L", "C", "C", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    for idx, var in enumerate(sorted(relevant_vars)):
        if var not in stats:
            continue
        s = stats[var]
        unit = _UNITS.get(var, "")
        var_name = _VAR_NAMES.get(var, var)
        draw_row(
            pdf, col_widths, col_aligns,
            [
                var_name,
                f"{s['avg']:.1f} {unit}".strip(),
                f"{s['min']:.1f} {unit}".strip(),
                f"{s['max']:.1f} {unit}".strip(),
            ],
            row_index=idx,
        )

    pdf.ln(6)


def _render_thresholds(
    pdf: Any, thresholds: dict, relevant_vars: set,
    _VAR_NAMES: dict, _UNITS: dict,
) -> None:
    if pdf.get_y() > 230:
        pdf.add_page()

    render_section_divider(pdf, "Umbrales de riesgo configurados")

    col_widths = [58, 38, 24, 24, 24, 22]
    col_headers = ["Variable", "Dirección", "Bajo", "Medio", "Alto", "Unidad"]
    col_aligns = ["L", "C", "C", "C", "C", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    dir_labels = {"higher": "Mayor es peor", "lower": "Menor es peor", "range": "Rango válido"}
    for idx, var in enumerate(sorted(relevant_vars)):
        if var not in thresholds:
            continue
        cfg = thresholds[var]
        unit = _UNITS.get(var, "")
        var_name = _VAR_NAMES.get(var, var)
        d = cfg.get("direction", "higher")
        if d == "range":
            draw_row(
                pdf, col_widths, col_aligns,
                [var_name, dir_labels.get(d, d), f"{cfg['low']}", "—", f"{cfg['high']}", unit],
                row_index=idx,
            )
        else:
            low = cfg.get("low", 0)
            med = cfg.get("medium", 0)
            high = cfg.get("high", 0)
            draw_row(
                pdf, col_widths, col_aligns,
                [var_name, dir_labels.get(d, d), str(low), str(med), str(high), unit],
                row_index=idx,
            )

    pdf.ln(4)


def _render_limits_section(
    pdf: Any,
    edificio_id: int,
    relevant_vars: set,
    _VAR_NAMES: dict,
    _UNITS: dict,
) -> None:
    from apps.limits.services import get_sensor_limits

    limits = get_sensor_limits(edificio_id)
    if not limits:
        return

    vars_with_limit = [v for v in sorted(relevant_vars) if v in limits]
    if not vars_with_limit:
        return

    if pdf.get_y() > 230:
        pdf.add_page()

    render_section_divider(pdf, "Límites físicos de operación")

    col_widths = [80, 36, 36, 38]
    col_headers = ["Variable", "Mínimo", "Máximo", "Unidad"]
    col_aligns  = ["L", "C", "C", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    for idx, var in enumerate(vars_with_limit):
        lo, hi   = limits[var]
        unit     = _UNITS.get(var, "")
        var_name = _VAR_NAMES.get(var, var)
        draw_row(
            pdf, col_widths, col_aligns,
            [var_name, f"{lo:.1f}", f"{hi:.1f}", unit],
            row_index=idx,
        )

    pdf.ln(4)
