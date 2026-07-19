import datetime as dt
import logging
from collections import OrderedDict
from typing import Any

from django.http import HttpRequest, HttpResponse

from apps.core.services.pdf_shared import safe_text, _pdf_font, draw_row
from apps.core.services.pdf_rendering import (
    _create_report_pdf,
    make_pdf_response,
    render_pdf_header,
    render_section_divider,
    render_summary_box,
    render_table_header,
)
from apps.sensors.sensor_config import USER_STATS_COLORS
from apps.users.services import build_user_data, _filter_users_query

logger_pdf = logging.getLogger(__name__)


def user_pdf_view(request: HttpRequest) -> HttpResponse:
    try:
        query = request.GET.get("q", "").strip()
        building_id = request.GET.get("edificio", "").strip()
        estado = request.GET.get("estado", "").strip()

        usuarios = _filter_users_query(query, building_id, estado, extra_fields=True)

        users = [{"rol": u.rol, **build_user_data(u)} for u in usuarios]

        groups_raw: dict[str, list[Any]] = {}
        for b in users:
            if b.get("edificios_list"):
                for ed in b["edificios_list"]:
                    key = ed["nombre"]
                    groups_raw.setdefault(key, []).append(b)
            else:
                groups_raw.setdefault("Sin edificio", []).append(b)
                
        sorted_keys = sorted(groups_raw.keys(), key=lambda x: (x == "Sin edificio", x.lower()))
        groups = OrderedDict((k, groups_raw[k]) for k in sorted_keys)

        now = dt.datetime.now()
        pdf = _create_report_pdf("Reporte de usuarios")

        filtros: list[str] = []
        if query:
            filtros.append(f"Búsqueda: «{query}»")
        if estado:
            estado_labels = {
                "registrado": "Registrados",
                "por_registrar": "Pendientes de registro",
            }
            filtros.append(f"Estado: {estado_labels.get(estado, estado)}")

        total_registrados = sum(1 for u in users if u["registered"])
        total_pendientes = len(users) - total_registrados

        render_pdf_header(
            pdf,
            title="Reporte de usuarios",
            now=now,
            meta_lines=[
                f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}",
                f"Total de usuarios: {len(users)}",
                f"Edificios: {len(groups)}",
                *filtros,
            ],
        )

        render_section_divider(pdf, "Resumen de usuarios")
        render_summary_box(
            pdf,
            items=[
                {
                    "label": "Total de usuarios",
                    "value": len(users),
                    "fill": USER_STATS_COLORS["total"]["fill"],
                    "text": USER_STATS_COLORS["total"]["text"],
                },
                {
                    "label": "Registrados",
                    "value": total_registrados,
                    "fill": USER_STATS_COLORS["registrados"]["fill"],
                    "text": USER_STATS_COLORS["registrados"]["text"],
                },
                {
                    "label": "Pendientes",
                    "value": total_pendientes,
                    "fill": USER_STATS_COLORS["pendientes"]["fill"],
                    "text": USER_STATS_COLORS["pendientes"]["text"],
                },
                {
                    "label": "Edificios",
                    "value": len(groups),
                    "fill": USER_STATS_COLORS["edificios"]["fill"],
                    "text": USER_STATS_COLORS["edificios"]["text"],
                },
            ],
        )

        if not groups:
            _pdf_font(pdf, "I", 10)
            pdf.set_text_color(95, 95, 95)
            pdf.cell(0, 9, safe_text("No se encontraron usuarios con los filtros aplicados."), ln=1)

        col_widths = [28, 32, 32, 70, 28]
        col_headers = ["Cédula", "Nombre", "Apellido", "Correo electrónico", "Estado"]
        col_aligns = ["C", "L", "L", "L", "C"]

        for building_name, members in groups.items():
            if pdf.get_y() > 230:
                pdf.add_page()

            render_section_divider(pdf, f"{building_name} ({len(members)} usuario(s))")
            render_table_header(pdf, col_widths, col_aligns, col_headers)

            _pdf_font(pdf, "", 9)
            pdf.set_draw_color(10, 10, 10)
            for idx, b in enumerate(members):
                estado_str = "Registrado" if b["registered"] else "Pendiente"

                if b["registered"]:
                    est_fill = USER_STATS_COLORS["registrados"]["fill"]
                    est_text = USER_STATS_COLORS["registrados"]["text"]
                else:
                    est_fill = USER_STATS_COLORS["pendientes"]["fill"]
                    est_text = USER_STATS_COLORS["pendientes"]["text"]

                draw_row(
                    pdf,
                    col_widths,
                    col_aligns,
                    [
                        str(b["cedula"]),
                        b["nombre"][:22],
                        b["last_name"][:22],
                        b["email"][:60],
                        estado_str,
                    ],
                    [None, None, None, None, est_fill],
                    [None, None, None, None, est_text],
                    row_index=idx,
                )

            pdf.ln(4)

        return make_pdf_response(pdf, f"reporte_usuarios_{now.strftime('%Y%m%d_%H%M%S')}.pdf")

    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain",
            status=500,
        )
    except Exception as e:
        logger_pdf.warning("User PDF generation failed: %s", e)
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain",
            status=500,
        )
