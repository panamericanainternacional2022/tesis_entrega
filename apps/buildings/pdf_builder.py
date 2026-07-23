import datetime as _dt_bld
from typing import Any

from django.shortcuts import get_object_or_404

from apps.buildings.models import Building, MonitoringEquipment
from apps.sensors.sensor_config import (
    RISK_NORMAL, RISK_ALTO, RISK_CRITICO,
    SEVERITY_LEVELS, SEVERITY_DISPLAY_LEVELS, RISK_STYLES,
    HISTORY_SEVERITY_DISPLAY_LEVELS,
    PUMP_VARS, ELEVATOR_VARS,
    VAR_NAMES, UNITS, STATS_VARS, VALUE_DISPLAY_ES)
from apps.history.models import History
from apps.core.services.risk_service import classify_risk
from apps.thresholds.services import get_thresholds
from apps.sensors.simulation.globals import simulators
from apps.core.services.pdf_shared import _pdf_font, draw_row, safe_text
from apps.core.services.pdf_rendering import (
    _create_report_pdf,
    render_pdf_header, render_section_divider, render_summary_box,
    render_severity_legend, render_table_header)

EQUIP_STATUS_STYLE: dict[str, tuple[tuple, tuple]] = {
    "operativo":    RISK_STYLES.get(RISK_NORMAL, ((240, 253, 244), (22, 163, 74))),
    "falla":        RISK_STYLES.get(RISK_CRITICO, ((254, 242, 242), (185, 28, 28))),
    "mantenimiento": RISK_STYLES.get(RISK_ALTO, ((255, 247, 237), (217, 119, 6))),
}
EQUIP_TYPE_ES: dict[str, str] = {
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
    equip_types = set()
    for eq in equipment:
        equip_types.add(eq.equipment_type)

    sensor_data = sim.sensor_data if sim else {}
    history = sim.history if sim else []
    stats = _compute_pdf_stats(history, STATS_VARS)

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
        ])

    _render_executive_summary(
        pdf, sensor_data, thresholds, relevant_vars)
    _render_equipment_summary(pdf, equipment)
    render_severity_legend(pdf)

    critical_items = _get_critical_items(
        sensor_data, thresholds, relevant_vars)
    if critical_items:
        _render_critical_section(pdf, critical_items, VAR_NAMES, UNITS, VALUE_DISPLAY_ES)

    _render_current_readings(
        pdf, sensor_data, thresholds, relevant_vars, equip_types, VAR_NAMES, UNITS, VALUE_DISPLAY_ES,
        sim.sim_faults if sim else None)

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


def _compute_pdf_stats(history: list, stats_vars: list) -> dict:
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
    sensor_data: dict, thresholds: dict, relevant_vars: set) -> list[dict]:
    _CRITICAL_LEVELS = {RISK_ALTO, RISK_CRITICO}
    items = []
    for var in sorted(relevant_vars):
        if var not in sensor_data:
            continue
        risk, _ = classify_risk(var, sensor_data[var], thresholds)
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
    relevant_vars: set) -> None:

    render_section_divider(pdf, "Resumen ejecutivo")

    counts = {rl: 0 for rl in list(SEVERITY_LEVELS) + [RISK_NORMAL]}
    for var in relevant_vars:
        if var in sensor_data:
            risk, _ = classify_risk(var, sensor_data[var], thresholds)
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


def _render_equipment_summary(
    pdf: Any,
    equipment: list) -> None:

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
        fill_c, text_c = EQUIP_STATUS_STYLE.get(status_raw, ((249, 250, 251), (55, 65, 81)))
        type_label = EQUIP_TYPE_ES.get(eq.equipment_type, eq.equipment_type.capitalize())
        status_label = status_raw.capitalize()

        draw_row(
            pdf, col_widths, col_aligns,
            [eq.name, type_label, status_label],
            [None, None, fill_c],
            [None, None, text_c],
            row_index=idx)

    pdf.ln(4)


def _render_critical_section(
    pdf: Any, critical_items: list[dict],
    _VAR_NAMES: dict, _UNITS: dict,
    _VALUE_DISPLAY_ES: dict = None) -> None:
    if pdf.get_y() > 230:
        pdf.add_page()

    render_section_divider(pdf, f"Sensores en estado {RISK_CRITICO} / {RISK_ALTO}")

    col_widths = [72, 50, 68]
    col_headers = ["Variable", "Valor", "Severidad"]
    col_aligns = ["L", "C", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    for idx, item in enumerate(critical_items):
        var = item["var"]
        val = item["value"]
        risk = item["risk"]
        val_str = _format_value(var, val, _UNITS, _VALUE_DISPLAY_ES)
        var_name = _VAR_NAMES.get(var, var)
        fill_c, text_c = RISK_STYLES.get(risk, ((255, 255, 255), (26, 26, 26)))

        draw_row(
            pdf, col_widths, col_aligns,
            [var_name, val_str, risk],
            [None, None, fill_c],
            [None, None, text_c],
            row_index=idx)

    pdf.ln(4)


def _render_current_readings(
    pdf: Any, sensor_data: dict, thresholds: dict,
    relevant_vars: set, equip_types: set,
    _VAR_NAMES: dict, _UNITS: dict,
    _VALUE_DISPLAY_ES: dict = None,
    active_faults: dict = None) -> None:
    if pdf.get_y() > 230:
        pdf.add_page()

    render_section_divider(pdf, "Lecturas actuales de sensores")

    col_widths = [72, 50, 68]
    col_headers = ["Variable", "Valor", "Severidad"]
    col_aligns = ["L", "C", "C"]

    sections = []
    if "bomba" in equip_types:
        sections.append(("Bomba y Eléctricos", [v for v in PUMP_VARS if v in relevant_vars]))
    if "elevador" in equip_types:
        sections.append(("Elevador y Motor", [v for v in ELEVATOR_VARS if v in relevant_vars]))

    for section_name, vars_list in sections:
        if pdf.get_y() > 230:
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
            from apps.sensors.sensor_config import PUMP_VARS
            is_on = sensor_data.get("pump_on") if var in PUMP_VARS else sensor_data.get("elevator_on")
            sim_faults = sensor_data.get("sim_faults") if isinstance(sensor_data.get("sim_faults"), dict) else {}
            active_fault = sim_faults.get("pump") if var in PUMP_VARS else sim_faults.get("elevator")
            risk, _ = classify_risk(var, val, thresholds, is_on=is_on, active_fault=active_fault)
            val_str = _format_value(var, val, _UNITS, _VALUE_DISPLAY_ES)
            var_name = _VAR_NAMES.get(var, var)
            fill_c, text_c = RISK_STYLES.get(risk, ((255, 255, 255), (26, 26, 26)))

            draw_row(
                pdf, col_widths, col_aligns,
                [var_name, val_str, risk],
                [None, None, fill_c],
                [None, None, text_c],
                row_index=row_idx)
            row_idx += 1

        pdf.ln(4)


def _render_history_section(
    pdf: Any,
    edificio_id: int,
    usuario_id: int | None = None,
    usuario_rol: str = "US") -> None:
    from apps.history.shared import _build_history_query
    from apps.history.shared import parse_history

    if pdf.get_y() > 230:
        pdf.add_page()

    render_section_divider(pdf, "Historial en el período")

    if usuario_id:
        records, _ = _build_history_query(usuario_id, usuario_rol, str(edificio_id))
    else:
        records = History.objects.filter(
            monitoring_equipment__building_id=edificio_id)

    records = (
        records
        .select_related("monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )

    total = records.count()
    _pdf_font(pdf, "", 10)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(0, 7, safe_text(f"Historial completo: {total} registro(s)"), ln=1)
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
        _pdf_font(pdf, "I", 10)
        pdf.cell(0, 9, safe_text("No se encontraron eventos registrados para este edificio."), ln=1)
        pdf.ln(4)
        return

    col_widths = [140, 50]
    col_headers = ["Severidad", "Cantidad"]
    col_aligns = ["L", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    row_idx = 0
    for risk_lvl, fill, text_c, _desc in HISTORY_SEVERITY_DISPLAY_LEVELS:
        cnt = counts.get(risk_lvl, 0)
        if cnt == 0:
            continue
        draw_row(
            pdf, col_widths, col_aligns,
            [risk_lvl, str(cnt)],
            [fill, None],
            [text_c, None],
            row_index=row_idx)
        row_idx += 1

    pdf.ln(4)


def _render_stats_table(
    pdf: Any, stats: dict, relevant_vars: set,
    _VAR_NAMES: dict, _UNITS: dict) -> None:
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
            row_index=idx)

    pdf.ln(4)


def _render_thresholds(
    pdf: Any, thresholds: dict, relevant_vars: set,
    _VAR_NAMES: dict, _UNITS: dict) -> None:
    if pdf.get_y() > 230:
        pdf.add_page()

    render_section_divider(pdf, "Umbrales de riesgo configurados")

    col_widths = [72, 40, 40, 38]
    col_headers = ["Variable", "Umbral Alto", "Umbral Crítico", "Unidad"]
    col_aligns = ["L", "C", "C", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    for idx, var in enumerate(sorted(relevant_vars)):
        if var not in thresholds:
            continue
        cfg = thresholds[var]
        unit = _UNITS.get(var, "")
        var_name = _VAR_NAMES.get(var, var)
        d = cfg.get("direction", "higher")
        
        high = cfg.get("high", 0)
        critic = cfg.get("critic", 0)
        
        if d == "range":
            margin = (critic - high) * 0.20
            a_low = high + margin
            a_high = critic - margin
            draw_row(
                pdf, col_widths, col_aligns,
                [var_name, f"< {a_low:.1f} o > {a_high:.1f}", f"< {high} o > {critic}", unit],
                row_index=idx)
        elif d == "lower":
            draw_row(
                pdf, col_widths, col_aligns,
                [var_name, f"<= {high}", f"<= {critic}", unit],
                row_index=idx)
        else:
            draw_row(
                pdf, col_widths, col_aligns,
                [var_name, f">= {high}", f">= {critic}", unit],
                row_index=idx)

    pdf.ln(4)


def _render_limits_section(
    pdf: Any,
    edificio_id: int,
    relevant_vars: set,
    _VAR_NAMES: dict,
    _UNITS: dict) -> None:
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
    col_headers = ["Variable", "Mín. fijo", "Máximo", "Unidad"]
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
            row_index=idx)

    pdf.ln(4)
