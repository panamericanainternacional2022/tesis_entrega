import logging
import os
import unicodedata
from typing import Any


PERIOD_LABEL_MAP: dict[str, str] = {
    "reciente": "Más reciente",
    "antiguo": "Más antiguo",
}

logger = logging.getLogger(__name__)

FONT_SEARCH_PATHS: list[str] = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/ARIAL.TTF",
]

_FONT_CACHE: dict[str, str] = {}


def _get_period_label(period: str, date_from_raw: str, date_to_raw: str) -> str:
    if period == "custom":
        return f"Personalizado: {date_from_raw or '?'} al {date_to_raw or '?'}"
    if period in PERIOD_LABEL_MAP:
        return PERIOD_LABEL_MAP[period]
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
        t_str = unicodedata.normalize("NFKD", t_str)
        t_str = t_str.encode("ascii", errors="replace").decode("ascii")
    return t_str


_ZEBRA_FILL: tuple[int, int, int] = (249, 250, 251)

_CELL_PAD_H: float = 2.5
_CELL_PAD_V: float = 1.2


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

    inner_widths = [max(w - 2 * _CELL_PAD_H, 4.0) for w in widths]

    lines_per_col: list[list[str]] = []
    for iw, text in zip(inner_widths, data):
        t_str = safe_text(text)
        lines = pdf.multi_cell(iw, 4, t_str, split_only=True)
        lines_per_col.append(lines)

    max_lines = max(len(lines) for lines in lines_per_col) if lines_per_col else 1
    line_height: float = 5.8
    row_height: float = max_lines * line_height + 2 * _CELL_PAD_V

    if pdf.get_y() + row_height > 270:
        pdf.add_page()

    start_x: float = pdf.get_x()
    start_y: float = pdf.get_y()

    curr_x = start_x
    for j, w in enumerate(widths):
        explicit_fill = fills[j] if (fills and fills[j]) else None
        effective_fill = explicit_fill if explicit_fill else zebra
        if effective_fill:
            pdf.set_fill_color(*effective_fill)
            pdf.rect(curr_x, start_y, w, row_height, "F")
        curr_x += w

    for i in range(max_lines):
        curr_x = start_x
        for j, lines in enumerate(lines_per_col):
            iw = inner_widths[j]
            align = aligns[j]
            txt = lines[i] if i < len(lines) else ""
            text_c = colors[j] if (colors and colors[j]) else (26, 26, 26)
            pdf.set_text_color(*text_c)
            text_x = curr_x + _CELL_PAD_H
            text_y = start_y + _CELL_PAD_V + i * line_height
            pdf.set_xy(text_x, text_y)
            pdf.cell(iw, line_height, txt, border=0, align=align, fill=False)
            curr_x += widths[j]

    curr_x = start_x
    pdf.set_draw_color(10, 10, 10)
    for w in widths:
        pdf.rect(curr_x, start_y, w, row_height)
        curr_x += w

    pdf.set_xy(start_x, start_y + row_height)
