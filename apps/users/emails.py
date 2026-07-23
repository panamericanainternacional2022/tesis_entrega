import json
import logging
import re
import smtplib
import time as time_module
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.buildings.models import Building, UserBuilding
from apps.buildings.pdf_builder import generate_building_report_bytes
from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_error, json_ok
from apps.history.services.email_recipients import get_building_emails
from apps.history.services.email_templates import build_report_email_html
from apps.history.services.email_sender import send_email_raw
from apps.sensors.simulation.globals import simulators
from apps.users.models import Usuario

logger_email = logging.getLogger(__name__)


def _build_report_email_body(building: Any = None, sim: Any = None) -> tuple[str, str]:
    timestamp = time_module.strftime("%d/%m/%Y %H:%M:%S")
    edificio_nombre = ""
    if building:
        edificio_nombre = getattr(building, "name", "")
    elif sim:
        edificio_nombre = getattr(sim, "nombre", "") or ""

    subject = (
        f"Reporte de monitoreo: {edificio_nombre} - {timestamp}"
        if edificio_nombre
        else f"Reporte de monitoreo - {timestamp}"
    )
    body = build_report_email_html(edificio=edificio_nombre)
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


def _send_user_report(user: Usuario, request: HttpRequest) -> JsonResponse | None:
    person = user.id_persona
    email = person.email if person else ""
    if not email:
        return json_error("El usuario no tiene un correo electrónico registrado.", 400)

    assignments = list(
        UserBuilding.objects.filter(user=user).select_related("building")
    )
    buildings = [ue.building for ue in assignments if ue.building]

    if not buildings:
        return json_error("El usuario no tiene ningún edificio asignado.", 400)

    timestamp = time_module.strftime("%d/%m/%Y %H:%M:%S")
    b_names = [b.name for b in buildings]
    b_names_str = ", ".join(b_names)

    if len(buildings) == 1:
        subject = f"Reporte de monitoreo: {b_names_str} - {timestamp}"
        html_body = build_report_email_html(edificio=b_names_str)
    else:
        subject = f"Reporte de monitoreo: {b_names_str} - {timestamp}"
        ctx = (
            f"Se adjuntan los informes en formato PDF con el estado actual de los "
            f"sensores de infraestructura para los siguientes edificios: {b_names_str}. "
            f"Los documentos incluyen las lecturas más recientes, las estadísticas de "
            f"operación y un resumen del nivel de riesgo de cada parámetro monitoreado por edificio."
        )
        html_body = build_report_email_html(contexto=ctx)

    attachments = []
    for b in buildings:
        try:
            pdf_bytes, pdf_name = generate_building_report_bytes(b.id, request)
            if pdf_bytes:
                attachments.append((pdf_bytes, pdf_name))
        except Exception as e:
            logger_email.warning("Could not generate building report PDF for building %s: %s", b.id, e)

    if not attachments:
        return json_error("No se pudo generar el reporte PDF para los edificios del usuario.", 500)

    try:
        send_email_raw(
            to_addrs=[email],
            subject=subject,
            html_body=html_body,
            attachments=attachments,
        )
    except Exception as exc:
        logger_email.error("send report failed: %s", exc)
        return json_error(_smtp_error_message(exc), 502)

    return None


def _send_report_to_recipients(
    to_addrs: list[str], edificio_id: int | None, request: HttpRequest
) -> JsonResponse | None:
    building = None
    if edificio_id:
        building = Building.objects.filter(id=edificio_id).first()
    if not building:
        sim = simulators.get(edificio_id) if edificio_id else next(iter(simulators.values()), None)
        if sim:
            actual_eid = sim.edificio_id
            building = Building.objects.filter(id=actual_eid).first()

    if not building:
        return json_error("No se encontró información del edificio especificado.", 404)

    actual_eid = building.id
    sim = simulators.get(actual_eid)
    subject, html_body = _build_report_email_body(building, sim)

    pdf_bytes = None
    pdf_name = "reporte.pdf"
    try:
        pdf_bytes, pdf_name = generate_building_report_bytes(actual_eid, request)
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

    email = data.get("email", "").strip()
    user_id = _safe_int(data.get("user_id"))

    user = None
    if user_id:
        user = Usuario.objects.filter(id_usuario=user_id).first()
    if not user and email:
        user = Usuario.objects.filter(id_persona__email=email).first()

    if user:
        error = _send_user_report(user, request)
        if error:
            return error
        target_email = user.id_persona.email if user.id_persona else email
        return json_ok({"message": f"Reporte enviado a {target_email}"})

    if not email:
        return json_error("Missing field 'email'")
    if not re.match(r"^[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*@[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)+$", email):
        return json_error("El correo electrónico no tiene un formato válido.")

    eid = _safe_int(data.get("edificio_id"))
    error = _send_report_to_recipients([email], eid, request)
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
