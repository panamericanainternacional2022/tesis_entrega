import logging
from typing import Any

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required
from apps.core.services.http_request import get_building_id_param
from apps.core.services.http_response import json_ok
from apps.buildings.models import Building
from apps.history.models import History
from apps.history.shared import _build_history_query
from apps.sensors.sensor_config import PAGE_SIZE
from apps.dashboard.shared import (
    filter_date_range, build_query_string,
    parse_history, extract_variables,
    extract_severities, filter_severity_python, filter_by_variable,
)
from apps.core.services.pdf_shared import _pdf_font, safe_text, _get_period_label, draw_row
from apps.core.services.pdf_rendering import (
    _create_report_pdf,
    get_column_config,
    make_pdf_response,
    render_event_rows,
    render_pdf_header,
    render_section_divider,
    render_severity_legend,
    render_stats_summary,
    render_table_header,
)

logger = logging.getLogger(__name__)


@login_required
def history_view(request: HttpRequest):
    from apps.core.auth_decorators import is_admin_role
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return render(request, "history/history.html", {
            "records": None, "edificios": [], "rol": "US",
            "filter_query_string": "",
            "severidad": "", "variable_filter": "", "all_variables": [],
            "ALL_SEVERITIES": [], "fecha_desde": "", "fecha_hasta": "",
            "periodo_seleccionado": "1h", "total_count": 0,
        })

    rol = request.session.get("usuario_rol", "US")
    building_id_raw = get_building_id_param(request, "building", "edificio")
    severity = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    period = request.GET.get("periodo", "1h").strip()
    date_from = request.GET.get("fecha_desde", "").strip()
    date_to = request.GET.get("fecha_hasta", "").strip()

    filter_params = {}
    if building_id_raw and building_id_raw.isdigit():
        filter_params["edificio"] = building_id_raw

    records, _ = _build_history_query(usuario_id, rol, building_id_raw)

    if is_admin_role(rol):
        buildings = Building.objects.all()
    else:
        from apps.buildings.models import UserBuilding
        user_building_ids = UserBuilding.objects.filter(
            user_id=usuario_id
        ).values_list("building", flat=True)
        buildings = Building.objects.filter(id__in=user_building_ids)

    # Total global sin filtrar por fecha/severidad/variable (para el badge)
    total_count = records.distinct().count()

    records = filter_date_range(records, period, date_from, date_to)

    records = (
        records
        .select_related("user", "monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )

    parsed_list = parse_history(records)

    all_variables = extract_variables(parsed_list)
    available_severities = extract_severities(parsed_list)

    parsed_list = filter_severity_python(parsed_list, severity)
    parsed_list = filter_by_variable(parsed_list, variable_filter)

    query_string = build_query_string(
        edificio=building_id_raw,
        severidad=severity,
        variable=variable_filter,
        periodo=period,
        fecha_desde=date_from if period == "custom" else None,
        fecha_hasta=date_to if period == "custom" else None,
    )

    paginator = Paginator(parsed_list, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "history/history.html",
        {
            "records": page_obj,
            "edificios": buildings,
            "selected_edificio_id": int(building_id_raw) if building_id_raw and building_id_raw.isdigit() else None,
            "rol": rol,
            "filter_query_string": query_string,
            "severidad": severity,
            "variable_filter": variable_filter,
            "all_variables": all_variables,
            "ALL_SEVERITIES": available_severities,
            "fecha_desde": date_from,
            "fecha_hasta": date_to,
            "periodo_seleccionado": period,
            "total_count": total_count,
        },
    )


@require_http_methods(["GET"])
def view_unread_count(request: HttpRequest) -> JsonResponse:
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return json_ok({"count": 0})

    rol = request.session.get("usuario_rol", "US")
    records, _ = _build_history_query(usuario_id, rol)

    return json_ok({"count": records.distinct().count()})


@login_required
@require_http_methods(["POST"])
def clear_history_view(request: HttpRequest) -> JsonResponse:
    usuario_id = request.session.get("usuario_id")
    if usuario_id:
        History.objects.filter(user_id=usuario_id).delete()
    return json_ok({"message": "History cleared successfully"})


# ── History PDF Report (moved from reports.views.history) ──────────────────


@login_required
def history_pdf_view(request: Any) -> HttpResponse:
    import datetime as dt
    from collections import OrderedDict

    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return HttpResponse("No autorizado", status=401)

    rol = request.session.get("usuario_rol", "US")
    building_id_raw = get_building_id_param(request, "building", "edificio")

    severity       = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    period         = request.GET.get("periodo", "1h").strip()
    date_from      = request.GET.get("fecha_desde", "").strip()
    date_to        = request.GET.get("fecha_hasta", "").strip()

    records, building_name = _build_history_query(usuario_id, rol, building_id_raw)

    records = filter_date_range(records, period, date_from, date_to)

    records = (
        records
        .select_related("user", "monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )
    parsed_list = parse_history(records)

    parsed_list = filter_severity_python(parsed_list, severity)
    parsed_list = filter_by_variable(parsed_list, variable_filter)

    range_label = _get_period_label(period, date_from, date_to)
    if not building_name:
        building_name = building_id_raw or "Todos los edificios"

    try:
        pdf = _create_report_pdf("Historial")
        now = dt.datetime.now()

        render_pdf_header(
            pdf,
            title="Historial",
            now=now,
            meta_lines=[
                f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}",
                f"Edificio: {building_name}",
                f"Severidad: {severity if severity else 'Todas'}",
                f"Variable: {variable_filter if variable_filter else 'Todas'}",
                f"Período: {range_label}",
                (
                    f"Rango personalizado: {date_from} al {date_to}"
                    if date_from and date_to
                    else None
                ),
                f"Total de eventos: {len(parsed_list)}",
            ],
        )

        if parsed_list:
            render_stats_summary(pdf, parsed_list)

        render_severity_legend(pdf)

        groups: OrderedDict[str, list[Any]] = OrderedDict()
        for n in parsed_list:
            bld = (
                n.monitoring_equipment.building.name
                if (n.monitoring_equipment and n.monitoring_equipment.building)
                else "Sin edificio"
            )
            groups.setdefault(bld, []).append(n)

        if len(groups) > 1:
            _render_building_summary(pdf, groups)

        column_widths, column_headers, column_aligns = get_column_config()

        if parsed_list:
            for group_name, group_events in groups.items():
                if pdf.get_y() > 240:
                    pdf.add_page()

                render_section_divider(pdf, f"{group_name} ({len(group_events)} evento(s))")
                render_table_header(pdf, column_widths, column_aligns, column_headers)
                render_event_rows(pdf, group_events, column_widths, column_aligns)
                pdf.ln(4)
        else:
            _pdf_font(pdf, "I", 10)
            pdf.set_text_color(95, 95, 95)
            pdf.cell(0, 9, safe_text("No se encontraron eventos con los filtros aplicados."), ln=1)

        filename = f"historial_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
        return make_pdf_response(pdf, filename)

    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain",
            status=500,
        )
    except Exception as e:
        logger.warning("History PDF generation failed: %s", e)
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain",
            status=500,
        )


def _render_building_summary(pdf: Any, groups: dict) -> None:
    render_section_divider(pdf, "Distribución de eventos por edificio")

    col_widths = [120, 30, 40]
    col_headers = ["Edificio", "Eventos", "% del total"]
    col_aligns = ["L", "C", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    total_events = sum(len(v) for v in groups.values())

    for idx, (bld_name, events) in enumerate(groups.items()):
        count = len(events)
        pct = (count / total_events * 100) if total_events else 0
        draw_row(
            pdf,
            col_widths,
            col_aligns,
            [bld_name, str(count), f"{pct:.1f}%"],
            row_index=idx,
        )

    pdf.ln(6)
