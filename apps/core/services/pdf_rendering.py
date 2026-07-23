import datetime as dt
from typing import Any

from django.http import HttpResponse

from apps.sensors.sensor_config import (
    MAX_PDF_EVENTS,
    RISK_STYLES,
    SEVERITY_DISPLAY_LEVELS,
)
from apps.core.services.pdf_shared import (
    _pdf_font,
    draw_row,
    safe_text,
)

ACCENT_COLOR = (37, 99, 235)

DIVIDER_COLOR = (200, 205, 212)
HEADER_BG     = (10, 10, 10)
HEADER_TEXT   = (255, 255, 255)


def render_logo(pdf: Any) -> None:

    y0 = pdf.get_y()

    pdf.set_fill_color(*ACCENT_COLOR)
    pdf.rect(10, y0, 4, 22, "F")

    pdf.set_x(17)
    _pdf_font(pdf, "B", 28)
    pdf.set_text_color(*ACCENT_COLOR)
    pdf.cell(0, 14, "INES", ln=1, align="L")

    pdf.set_x(17)
    _pdf_font(pdf, "", 10)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 8, safe_text("Sistema inteligente en monitoreo"), ln=1, align="L")
    pdf.ln(2)

    pdf.set_draw_color(*DIVIDER_COLOR)
    pdf.set_line_width(0.5)
    y = pdf.get_y()
    pdf.line(10, y, 200, y)
    pdf.set_line_width(0.6)
    pdf.ln(6)


def render_pdf_header(
    pdf: Any,
    title: str,
    now: dt.datetime,
    meta_lines: list,
) -> None:

    render_logo(pdf)
    _pdf_font(pdf, "B", 18)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, safe_text(title), ln=1, align="L")
    _pdf_font(pdf, "", 11)
    pdf.set_text_color(26, 26, 26)
    for line in meta_lines:
        if line is not None:
            pdf.cell(0, 7, safe_text(line), ln=1)
    pdf.ln(6)


def render_section_divider(pdf: Any, title: str) -> None:

    if pdf.get_y() > 230:
        pdf.add_page()
    pdf.ln(2)
    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(*ACCENT_COLOR)
    pdf.cell(0, 9, safe_text(title), ln=1)
    pdf.set_draw_color(*DIVIDER_COLOR)
    pdf.set_line_width(0.4)
    y = pdf.get_y()
    pdf.line(10, y, 200, y)
    pdf.set_line_width(0.6)
    pdf.ln(3)


def render_summary_box(pdf: Any, items: list) -> None:

    if not items:
        return

    n = len(items)
    cell_w = 190 // n
    start_x = pdf.get_x()
    start_y = pdf.get_y()
    box_h = 16

    if start_y + box_h > 270:
        pdf.add_page()
        start_y = pdf.get_y()

    pdf.set_draw_color(*HEADER_BG)

    for i, item in enumerate(items):
        fill = item.get("fill", (249, 250, 251))
        pdf.set_fill_color(*fill)
        x = start_x + i * cell_w
        pdf.rect(x, start_y, cell_w, box_h, "DF")

    _pdf_font(pdf, "", 8)
    for i, item in enumerate(items):
        text_c = item.get("text", (10, 10, 10))
        label = item.get("label", "")
        pdf.set_xy(start_x + i * cell_w + 3, start_y + 2)
        pdf.set_text_color(*text_c)
        pdf.cell(cell_w - 3, 5, safe_text(label), ln=0)

    _pdf_font(pdf, "B", 12)
    for i, item in enumerate(items):
        text_c = item.get("text", (10, 10, 10))
        value = str(item.get("value", ""))
        pdf.set_xy(start_x + i * cell_w + 3, start_y + 8)
        pdf.set_text_color(*text_c)
        pdf.cell(cell_w - 3, 7, safe_text(value), ln=0)

    pdf.set_xy(start_x, start_y + box_h + 4)


def render_severity_legend(pdf: Any, severity_levels=None) -> None:
    if severity_levels is None:
        severity_levels = SEVERITY_DISPLAY_LEVELS

    render_section_divider(pdf, "Leyenda de severidades")
    _pdf_font(pdf, "", 10)

    row_h   = 9
    pad_h   = 2.5
    pad_v   = 1.5
    w_lbl   = 36
    w_desc  = 154

    for lbl, fill, text_c, desc in severity_levels:
        x0 = pdf.get_x()
        y0 = pdf.get_y()

        pdf.set_fill_color(*fill)
        pdf.set_draw_color(10, 10, 10)
        pdf.rect(x0, y0, w_lbl, row_h, "DF")

        pdf.set_fill_color(255, 255, 255)
        pdf.rect(x0 + w_lbl, y0, w_desc, row_h, "DF")

        pdf.set_xy(x0 + pad_h, y0 + pad_v)
        pdf.set_text_color(*text_c)
        pdf.cell(w_lbl - 2 * pad_h, row_h - 2 * pad_v, safe_text(lbl), 0, 0, "L")

        pdf.set_xy(x0 + w_lbl + pad_h, y0 + pad_v)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(w_desc - 2 * pad_h, row_h - 2 * pad_v, safe_text(desc), 0, 0, "L")

        pdf.set_xy(x0, y0 + row_h)

    pdf.ln(6)



def render_stats_summary(pdf: Any, parsed_list: list, severity_levels=None) -> None:
    if severity_levels is None:
        severity_levels = SEVERITY_DISPLAY_LEVELS

    stats: dict[str, int] = {s[0]: 0 for s in severity_levels}
    for n in parsed_list:
        risk = n.parsed_data.get("risk", "")
        if risk in stats:
            stats[risk] += 1

    render_section_divider(pdf, "Resumen por severidad")

    items = [
        {
            "label": lbl,
            "value": stats.get(lbl, 0),
            "fill": fill,
            "text": text_c,
        }
        for lbl, fill, text_c, _desc in severity_levels
    ]
    render_summary_box(pdf, items)


def get_column_config() -> tuple[list, list, list]:
    return (
        [48, 36, 28, 50, 28],
        ["Fecha y hora", "Equipo", "Severidad", "Variable", "Valor"],
        ["L", "L", "C", "L", "C"],
    )


def render_table_header(
    pdf: Any,
    column_widths: list,
    column_aligns: list,
    column_headers: list,
) -> None:

    _pdf_font(pdf, "B", 10)
    draw_row(
        pdf,
        column_widths,
        column_aligns,
        column_headers,
        fills=[HEADER_BG] * len(column_widths),
        colors=[HEADER_TEXT] * len(column_widths),
    )


def _create_report_pdf(title: str) -> Any:

    from fpdf import FPDF

    class _ReportPDF(FPDF):
        _title = title

        def header(self) -> None:
            if self.page_no() == 1:
                self.set_fill_color(*ACCENT_COLOR)
                self.rect(10, 10, 190, 2, "F")
                self.ln(5)
            else:
                _pdf_font(self, "I", 9)
                self.set_text_color(95, 95, 95)
                title_text = safe_text(f"INES - {self._title}")
                page_text = safe_text(f"Pagina {self.page_no()} / {{nb}}")
                self.cell(0, 10, title_text, 0, 0, "L")
                self.cell(0, 10, page_text, 0, 1, "R")
                self.set_draw_color(*DIVIDER_COLOR)
                self.set_line_width(0.5)
                self.line(10, 18, 200, 18)
                self.ln(2)

        def footer(self) -> None:
            self.set_y(-15)
            _pdf_font(self, "I", 9)
            self.set_text_color(95, 95, 95)
            footer_text = safe_text(
                f"INES * Sistema inteligente en monitoreo"
                f"  * Página {self.page_no()} / {{nb}}"
            )
            self.cell(0, 10, footer_text, 0, 0, "C")

    pdf = _ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_line_width(0.6)
    pdf.add_page()
    return pdf


def make_pdf_response(pdf: Any, filename: str) -> HttpResponse:
    pdf_raw = pdf.output()
    pdf_bytes = (
        bytes(pdf_raw)
        if isinstance(pdf_raw, (bytearray, memoryview))
        else pdf_raw.encode("utf-8")
        if isinstance(pdf_raw, str)
        else bytes(pdf_raw)
    )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _get_equipment_name(notif: Any) -> str:
    if notif.monitoring_equipment:
        name = notif.monitoring_equipment.name or ""
        if " - " in name:
            name = name.split(" - ")[0].strip()
        elif "-" in name:
            name = name.split("-")[0].strip()
        return name or notif.monitoring_equipment.get_equipment_type_display()
    return "N/A"


def render_event_rows(
    pdf: Any,
    parsed_list: list,
    column_widths: list,
    column_aligns: list,
) -> None:

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)

    if len(parsed_list) > MAX_PDF_EVENTS:
        _pdf_font(pdf, "I", 9)
        pdf.set_text_color(194, 65, 12)
        pdf.cell(
            0, 6,
            safe_text(f"Mostrando los primeros {MAX_PDF_EVENTS} de {len(parsed_list)} eventos totales."),
            ln=1,
        )
        pdf.ln(2)

    for idx, notif in enumerate(parsed_list[:MAX_PDF_EVENTS]):
        risk = notif.parsed_data.get("risk", "")
        fill_c, text_c = RISK_STYLES.get(risk, ((255, 255, 255), (26, 26, 26)))

        date_str = notif.date.strftime("%d/%m/%Y %H:%M") if notif.date else ""
        variable_str = notif.parsed_data.get("variable", "")
        value_str = notif.parsed_data.get("value", "")
        if value_str and value_str.lower() not in ("true", "false", "none", ""):
            unit = notif.parsed_data.get("unit", "")
            value_str = f"{value_str} {unit}".strip()
        equip_str = _get_equipment_name(notif)

        row_data = [date_str, equip_str, risk, variable_str, value_str]
        cell_fills = [None, None, fill_c, None, None]
        cell_colors = [None, None, text_c, None, None]

        draw_row(
            pdf, column_widths, column_aligns,
            row_data, cell_fills, cell_colors,
            row_index=idx,
        )
