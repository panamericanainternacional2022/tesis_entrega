import json
import logging
import smtplib
import time as time_module
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.buildings.pdf_builder import generate_building_report_bytes
from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_error, json_ok
from apps.history.services.email_recipients import get_building_emails
from apps.history.services.email_templates import build_report_email_html
from apps.history.services.email_sender import send_email_raw
from apps.sensors.simulation.globals import simulators

logger_email = logging.getLogger(__name__)


def _build_report_email_body(sim) -> tuple[str, str]:
    timestamp = time_module.strftime("%d/%m/%Y %H:%M:%S")
    edificio = getattr(sim, "nombre", "") or ""
    subject = f"Reporte de monitoreo: {edificio} — {timestamp}" if edificio else f"Reporte de monitoreo — {timestamp}"
    body = build_report_email_html(edificio=edificio)
    return subject, body


def _smtp_error_message(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPDataError):
        code = exc.args[0]
        raw = exc.args[1]
        msg = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
        if code == 550 and "limit" in msg.lower():
            return "Límite diario de envío de Gmail excedido. Intente mañana o reduzca la frecuencia de notificaciones."
        return f"Error SMTP ({code}): {msg[:200]}"
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "Error de autenticación SMTP. Verifique las credenciales en el archivo .env."
    if isinstance(exc, smtplib.SMTPConnectError):
        return "No se pudo conectar al servidor SMTP. Verifique SMTP_SERVER y SMTP_PORT."
    return f"Error al enviar correo: {type(exc).__name__}: {exc}"


def _parse_json_body(request: HttpRequest) -> dict | None:
    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        return None


def _safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _send_report_to_recipients(
    to_addrs: list[str], edificio_id: int | None, request: HttpRequest
) -> JsonResponse | None:
    sim = simulators.get(edificio_id) if edificio_id else next(iter(simulators.values()), None)
    if not sim:
        return json_error("No hay un simulador activo. Inicie la simulación primero.", 503)

    actual_eid = sim.edificio_id
    subject, html_body = _build_report_email_body(sim)

    pdf_bytes = None
    pdf_name = "reporte.pdf"
    try:
        pdf_bytes, pdf_name = generate_building_report_bytes(actual_eid)
    except Exception as e:
        logger_email.warning("Could not generate building report PDF: %s", e)

    try:
        send_email_raw(
            to_addrs=to_addrs,
            subject=subject,
            html_body=html_body,
            attachment_pdf=pdf_bytes,
            attachment_name=pdf_name,
        )
    except Exception as exc:
        logger_email.error("send report failed: %s", exc)
        return json_error(_smtp_error_message(exc), 502)

    return None


@require_http_methods(["POST"])
@login_required
@admin_required
def send_test_email(request: HttpRequest) -> JsonResponse:
    data = _parse_json_body(request)
    if data is None:
        return json_error("Invalid JSON")

    email = data.get("email", "")
    if not email:
        return json_error("Missing field 'email'")

    error = _send_report_to_recipients([email], None, request)
    return error if error else json_ok({"message": f"Reporte enviado a {email}"})


@require_http_methods(["POST"])
@login_required
@admin_required
def send_all_subscribers(request: HttpRequest) -> JsonResponse:
    data = _parse_json_body(request)
    if data is None:
        return json_error("Invalid JSON")

    eid = _safe_int(data.get("edificio_id"))
    emails = get_building_emails(eid)
    if not emails:
        return json_error("No subscribers for this building")

    error = _send_report_to_recipients(emails, eid, request)
    return error if error else json_ok({"message": f"Reporte enviado a {len(emails)} suscriptores"})
