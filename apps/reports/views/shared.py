import datetime as dt
import logging
import os
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.events.models import Notification
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
from apps.sensors.sensor_config import (
    RISK_INFORMATIVO, RISK_ALTO, RISK_CRITICO,
    SEVERITY_LEVELS, MAX_PDF_EVENTS,
    SEVERITY_DISPLAY_LEVELS, RISK_STYLES,
)
from apps.core.date_utils import PERIOD_DELTA_MAP, PERIOD_LABEL_MAP

logger = logging.getLogger(__name__)

ALL_SEVERITY_LEVELS: list[str] = SEVERITY_LEVELS

FONT_SEARCH_PATHS: list[str] = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/ARIAL.TTF",
]

_FONT_CACHE: dict[str, str] = {}


def _get_user_info(request: Any) -> tuple[int | None, str]:
    user_id: int | None = request.session.get("usuario_id")
    role: str = request.session.get("usuario_rol", "US")
    return user_id, role


def _parse_query_params(request: Any) -> dict[str, str]:
    from apps.core.services.http_request import get_building_id_param
    building_id: str = get_building_id_param(request, "edificio")
    return {
        "building_id": building_id,
        "severity": request.GET.get("severidad", "").strip(),
        "variable": request.GET.get("variable", "").strip(),
        "period": request.GET.get("periodo", "24h").strip(),
        "date_from": request.GET.get("fecha_desde", "").strip(),
        "date_to": request.GET.get("fecha_hasta", "").strip(),
    }


def _filter_by_role_and_building(
    user_id: int | None,
    role: str,
    building_id: str,
) -> tuple[QuerySet, str]:
    from apps.events.shared import _build_notification_query
    if user_id is None:
        return Notification.objects.none(), ""
    notifications, building_name = _build_notification_query(user_id, role, building_id)
    if not building_name:
        building_name = building_id or "Todos los edificios"
    return notifications, building_name


def _apply_severity_filter(
    notifications: QuerySet, severity: str
) -> QuerySet:
    from apps.events.shared import filter_severity_include
    if severity:
        notifications = filter_severity_include(notifications, severity)
    return notifications


def _apply_period_filter(
    notifications: QuerySet,
    period: str,
    date_from_raw: str,
    date_to_raw: str,
) -> QuerySet:
    now = timezone.now()
    if period in PERIOD_DELTA_MAP:
        notifications = notifications.filter(date__gte=now - PERIOD_DELTA_MAP[period])
    elif period == "custom":
        if date_from_raw:
            try:
                naive = dt.datetime.strptime(date_from_raw, "%Y-%m-%d")
                notifications = notifications.filter(date__gte=timezone.make_aware(naive))
            except ValueError:
                pass
        if date_to_raw:
            try:
                naive = dt.datetime.strptime(date_to_raw, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                notifications = notifications.filter(date__lte=timezone.make_aware(naive))
            except ValueError:
                pass
    return notifications


def _parse_and_filter_notifications(
    notifications: QuerySet, variable: str
) -> list[Any]:
    from apps.events.shared import parse_notification_for_display

    notifications = (
        notifications.select_related("monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )

    parsed: list[Any] = []
    for notif in notifications:
        notif = parse_notification_for_display(notif)
        parsed.append(notif)

    if variable:
        parsed = [
            n for n in parsed
            if n.parsed_data.get("parsed") and n.parsed_data.get("variable") == variable
        ]
    return parsed


def _get_period_label(period: str, date_from_raw: str, date_to_raw: str) -> str:
    if period in PERIOD_LABEL_MAP:
        label = PERIOD_LABEL_MAP[period]
        if period == "custom":
            label = f"Personalizado: {date_from_raw or '?'} al {date_to_raw or '?'}"
        return label
    return period


def _resolve_font() -> dict[str, str]:
    if _FONT_CACHE:
        return _FONT_CACHE
    for path in FONT_SEARCH_PATHS:
        if os.path.exists(path):
            dir_path = os.path.dirname(path)
            base = os.path.splitext(os.path.basename(path))[0]
            family = "DejaVu" if "DejaVu" in base else "Arial"
            bold_path = os.path.join(dir_path, base.replace("Sans", "Sans-Bold") + ".ttf")
            if not os.path.exists(bold_path):
                bold_path = path
            _FONT_CACHE.update({"family": family, "path": path, "bold_path": bold_path})
            break
    return _FONT_CACHE


def _pdf_font(pdf: Any, style: str = "", size: int = 10) -> None:
    config = _resolve_font()
    if config:
        family: str = config["family"]
        font_path: str = config["bold_path"] if style == "B" else config["path"]
        pdf.add_font(family, style, font_path, uni=True)
        pdf.set_font(family, style, size)
    else:
        pdf.set_font("Helvetica", style, size)


def safe_text(txt: Any) -> str:
    if txt is None:
        return ""
    t_str = str(txt)
    if not _resolve_font():
        accents = {
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
            'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
            'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
            'í': 'i', 'ï': 'i', 'ö': 'o', 'ä': 'a',
            '\u201c': '"', '\u201d': '"',
            '\u2018': "'", '\u2019': "'",
            '\u2013': '-', '\u2014': '-',
            '\u2022': '*', '\u2026': '...',
        }
        for c, r in accents.items():
            t_str = t_str.replace(c, r)
        t_str = t_str.encode("latin-1", errors="replace").decode("latin-1")
    return t_str


_ZEBRA_FILL: tuple[int, int, int] = (248, 249, 250)

# Padding interno de celda (mm)
_CELL_PAD_H: float = 2.5   # horizontal (cada lado)
_CELL_PAD_V: float = 1.2   # vertical (arriba y abajo)


def draw_row(
    pdf: Any,
    widths: list[int],
    aligns: list[str],
    data: list[str],
    fills: list | None = None,
    colors: list | None = None,
    row_index: int | None = None,
) -> None:

    zebra = _ZEBRA_FILL if (row_index is not None and row_index % 2 == 0) else None

    # Ancho interno disponible para el texto (descuenta padding horizontal)
    inner_widths = [max(w - 2 * _CELL_PAD_H, 4.0) for w in widths]

    # Calcular cuántas líneas ocupa cada celda usando el ancho interno
    lines_per_col: list[list[str]] = []
    for iw, text in zip(inner_widths, data):
        t_str = safe_text(text)
        lines = pdf.multi_cell(iw, 4, t_str, split_only=True)
        lines_per_col.append(lines)

    max_lines = max(len(lines) for lines in lines_per_col) if lines_per_col else 1
    line_height: float = 5.8
    # Alto total de la fila = líneas * altura de línea + padding vertical (×2)
    row_height: float = max_lines * line_height + 2 * _CELL_PAD_V

    if pdf.get_y() + row_height > 270:
        pdf.add_page()

    start_x: float = pdf.get_x()
    start_y: float = pdf.get_y()

    # ── Paso 1: rellenos de fondo (rectángulo completo por columna) ──────────
    curr_x = start_x
    for j, w in enumerate(widths):
        explicit_fill = fills[j] if (fills and fills[j]) else None
        effective_fill = explicit_fill if explicit_fill else zebra
        if effective_fill:
            pdf.set_fill_color(*effective_fill)
            pdf.rect(curr_x, start_y, w, row_height, "F")
        curr_x += w

    # ── Paso 2: texto con padding ────────────────────────────────────────────
    for i in range(max_lines):
        curr_x = start_x
        for j, lines in enumerate(lines_per_col):
            iw = inner_widths[j]
            align = aligns[j]
            txt = lines[i] if i < len(lines) else ""
            text_c = colors[j] if (colors and colors[j]) else (26, 26, 26)
            pdf.set_text_color(*text_c)
            # Desplazar X según alineación para respetar padding horizontal
            if align == "L":
                text_x = curr_x + _CELL_PAD_H
            elif align == "R":
                text_x = curr_x + _CELL_PAD_H
            else:  # "C"
                text_x = curr_x + _CELL_PAD_H
            text_y = start_y + _CELL_PAD_V + i * line_height
            pdf.set_xy(text_x, text_y)
            pdf.cell(iw, line_height, txt, border=0, align=align, fill=False)
            curr_x += widths[j]

    # ── Paso 3: bordes ───────────────────────────────────────────────────────
    curr_x = start_x
    pdf.set_draw_color(10, 10, 10)
    for w in widths:
        pdf.rect(curr_x, start_y, w, row_height)
        curr_x += w

    pdf.set_xy(start_x, start_y + row_height)

