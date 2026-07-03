from apps.reports.views.shared import draw_row
import datetime as dt
from typing import Any

from django.http import HttpResponse

from apps.core.auth_decorators import login_required

from .pdf_rendering import (
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
from .shared import (
    _get_period_label,
    _pdf_font,
    safe_text,
)


@login_required
def history_pdf_view(request: Any) -> HttpResponse:
    import datetime as dt
    from django.utils import timezone
    from apps.events.shared import _build_notification_query, parse_notification_for_display
    from apps.dashboard.shared import (
        filter_date_range, parse_notifications,
        filter_severity_python, filter_by_variable,
    )
    from apps.core.services.http_request import get_building_id_param

    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return HttpResponse("No autorizado", status=401)

    rol = request.session.get("usuario_rol", "US")
    building_id_raw = get_building_id_param(request, "building", "edificio")

    # Leer parámetros — mismos nombres que el template
    severity       = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    period         = request.GET.get("periodo", "1h").strip()
    date_from      = request.GET.get("fecha_desde", "").strip()
    date_to        = request.GET.get("fecha_hasta", "").strip()

    # 1. Obtener queryset base (mismo que notifications_view)
    notifications, building_name = _build_notification_query(usuario_id, rol, building_id_raw)

    # 2. Aplicar timestamp de "limpiar alertas" (idéntico al template)
    alerts_cleared_at = request.session.get("alerts_cleared_at")
    if alerts_cleared_at:
        cleared_dt = dt.datetime.fromtimestamp(alerts_cleared_at, tz=dt.timezone.utc)
        notifications = notifications.filter(date__gt=cleared_dt)

    # 3. Filtrar por rango de fecha (misma función del template)
    notifications = filter_date_range(notifications, period, date_from, date_to)

    # 4. Ordenar y parsear
    notifications = (
        notifications
        .select_related("user", "monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )
    parsed_list = parse_notifications(notifications)

    # 5. Filtrar severidad y variable en Python (igual que el template)
    parsed_list = filter_severity_python(parsed_list, severity)
    parsed_list = filter_by_variable(parsed_list, variable_filter)

    # Etiqueta del período para el encabezado
    range_label = _get_period_label(period, date_from, date_to)
    if not building_name:
        building_name = building_id_raw or "Todos los edificios"

    try:
        pdf = _create_report_pdf("Historial de eventos")
        now = dt.datetime.now()

        render_pdf_header(
            pdf,
            title="Historial de eventos",
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

        from collections import OrderedDict

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
