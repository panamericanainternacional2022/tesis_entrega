import datetime as dt
import json
import logging
import smtplib
import time as time_module
from collections import OrderedDict
from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.buildings.models import Building, UserBuilding
from apps.buildings.views import generate_building_report_bytes
from apps.core.auth_decorators import ADMIN_ROLES, login_required, admin_required
from apps.core.services.http_response import json_error, json_ok
from apps.core.services.pdf_shared import _pdf_font, draw_row
from apps.core.services.pdf_rendering import (
    _create_report_pdf,
    make_pdf_response,
    render_pdf_header,
    render_section_divider,
    render_summary_box,
    render_table_header,
)
from apps.history.services.email_sender import get_building_emails, build_report_email_html, send_email_raw
from apps.sensors.simulation.globals import simulators
from apps.users.models import Usuario, Persona
from apps.users.services import (
    build_user_data,
    generate_random_password,
    send_activation_email,
)
from apps.users.validators import validate_user_form, _validate_unique_ci
from .shared import (
    extract_post_data,
    has_required_fields,
    build_required_field_errors,
    create_user_with_retry,
    build_edit_initial_data,
)


def _filter_users_query(
    query: str = "", building_id: str = "", estado: str = "", extra_fields: bool = False
):
    qs = (
        Usuario.objects.select_related("id_persona")
        .prefetch_related("building_assignments__building")
        .exclude(rol__in=ADMIN_ROLES)
    )
    if building_id:
        qs = qs.filter(building_assignments__building_id=building_id)
    if estado == "registrado":
        qs = qs.filter(registered=True)
    elif estado == "por_registrar":
        qs = qs.filter(registered=False)
    if query:
        q = Q(id_persona__ci__icontains=query) | Q(id_persona__first_name__icontains=query) | Q(id_persona__middle_name__icontains=query) | Q(id_persona__first_last_name__icontains=query) | Q(id_persona__second_last_name__icontains=query)
        if extra_fields:
            q |= Q(id_persona__email__icontains=query) | Q(username__icontains=query) | Q(building_assignments__building__name__icontains=query)
        qs = qs.filter(q).distinct()
    return qs


@login_required
@admin_required
def user_list_view(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    building_id = request.GET.get("edificio", "").strip()
    estado = request.GET.get("estado", "").strip()

    users = [build_user_data(u) for u in _filter_users_query(query, building_id, estado)]
    buildings = list(Building.objects.all())

    has_mixed_estado = (
        any(u["registered"] for u in users) and any(not u["registered"] for u in users)
    ) if users else False
    filter_active = bool(building_id) or bool(estado) or bool(query)
    show_filter = filter_active or (bool(buildings) and bool(users) and (len(buildings) > 1 or has_mixed_estado))

    filter_params = {}
    if query:
        filter_params["q"] = query
    if building_id:
        filter_params["edificio"] = building_id
    if estado:
        filter_params["estado"] = estado
    filter_query_string = urlencode(filter_params)

    return render(request, "users/user_list.html", {
        "usuarios": users,
        "edificios": buildings,
        "selected_edificio_id": int(building_id) if building_id.isdigit() else None,
        "current_estado": estado,
        "filter_query_string": filter_query_string,
        "show_filter": show_filter,
    })


@login_required
@admin_required
@transaction.atomic
def user_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return render(request, "users/user_register.html", {"user": {}, "edificios": Building.objects.all()})

    generated_password = None
    user_data: dict[str, Any] = {}
    form_errors: dict[str, str] = {}
    email_sent = False
    activation_link = ""
    created_user = None

    if Building.objects.count() == 0:
        messages.error(request, "Debe registrar al menos un edificio antes de crear un usuario.")
    else:
        post_data = extract_post_data(request)
        user_data = post_data

        if not has_required_fields(post_data):
            messages.error(request, "Complete los campos obligatorios: nombre, apellido, correo electrónico, cédula y edificio.")
            form_errors = build_required_field_errors(post_data)
        else:
            form_errors = validate_user_form(post_data)
            if form_errors:
                messages.error(request, "Corrija los errores indicados en el formulario.")
            else:
                person = Persona.objects.create(
                    ci=post_data["cedula"],
                    first_name=post_data["primerNombre"],
                    middle_name=post_data["segundoNombre"],
                    first_last_name=post_data["primerApellido"],
                    second_last_name=post_data["segundoApellido"],
                    email=post_data["email"],
                )
                generated_password = generate_random_password(10)

                try:
                    created_user = create_user_with_retry(
                        post_data["primerNombre"],
                        post_data["primerApellido"],
                        generated_password,
                        person,
                    )
                except ValueError:
                    messages.error(request, "No se pudo generar el nombre de usuario. Verifique los datos ingresados.")
                    return render(request, "users/user_register.html", {"form_errors": form_errors, "edificios": Building.objects.all()})

                if post_data.get("id_edificio"):
                    UserBuilding.objects.create(user=created_user, building_id=post_data["id_edificio"])

                try:
                    activation_link = send_activation_email(
                        post_data["email"], created_user.id_usuario,
                        f"{'https' if request.is_secure() else 'http'}://{request.get_host()}",
                    )
                    email_sent = True
                except Exception:
                    token = signing.dumps({"user_id": created_user.id_usuario, "email": post_data["email"]})
                    activation_link = f"{'https' if request.is_secure() else 'http'}://{request.get_host()}{reverse('complete_registration')}?token={token}"

                person_name = person.get_full_name()
                if email_sent:
                    messages.success(request, f"{person_name} registrado. Se envió el correo de activación a {post_data['email']}.")
                else:
                    messages.warning(request, f"{person_name} registrado. No se pudo enviar el correo; entregue el enlace de activación manualmente: {activation_link}")

                return redirect("user_list")

    buildings = Building.objects.all()
    context: dict[str, Any] = {
        "user": user_data,
        "edificios": buildings,
        "form_errors": form_errors,
    }

    return render(request, "users/user_register.html", context)


@login_required
@admin_required
@transaction.atomic
def user_update_view(request: HttpRequest, user_id: int) -> HttpResponse:
    user = get_object_or_404(Usuario, id_usuario=user_id)
    person = user.id_persona
    form_errors: dict[str, str] = {}

    if request.method == "POST":
        post_data = extract_post_data(request)
        data = post_data

        if data.get("id_edificio") and data["id_edificio"].isdigit():
            data["id_edificio"] = int(data["id_edificio"])

        if not has_required_fields(post_data):
            messages.error(request, "Complete los campos obligatorios para actualizar: nombre, apellido, correo electrónico, cédula y edificio.")
            form_errors = build_required_field_errors(post_data)
        else:
            form_errors = validate_user_form(post_data, exclude_persona_id=person.id_persona)
            if form_errors:
                messages.error(request, "Corrija los errores indicados en el formulario.")
            else:
                person.first_name = post_data["primerNombre"]
                person.middle_name = post_data["segundoNombre"]
                person.first_last_name = post_data["primerApellido"]
                person.second_last_name = post_data["segundoApellido"]
                person.email = post_data["email"]
                person.ci = post_data["cedula"]
                person.save()

                UserBuilding.objects.filter(user=user).delete()
                if post_data.get("id_edificio"):
                    UserBuilding.objects.create(
                        user=user,
                        building_id=post_data["id_edificio"],
                    )

                full_name = person.get_full_name() or user.username

                if not user.registered:
                    try:
                        activation_link = send_activation_email(
                            person.email, user.id_usuario,
                            f"{'https' if request.is_secure() else 'http'}://{request.get_host()}",
                        )
                        messages.success(
                            request,
                            f"{full_name} actualizado. Se reenvió el correo de activación a {person.email}.",
                        )
                    except Exception:
                        token = signing.dumps({"user_id": user.id_usuario, "email": person.email})
                        activation_link = (
                            f"{'https' if request.is_secure() else 'http'}://{request.get_host()}"
                            f"{reverse('complete_registration')}?token={token}"
                        )
                        messages.warning(
                            request,
                            f"{full_name} actualizado. No se pudo enviar el correo; "
                            f"entregue el enlace de activación manualmente: {activation_link}",
                        )
                else:
                    messages.success(request, f"{full_name} actualizado correctamente.")

                return redirect("user_list")
    else:
        data = build_edit_initial_data(user, person)

    current_ue = UserBuilding.objects.filter(user=user).first()
    current_building = current_ue.building if current_ue else None
    buildings = Building.objects.all()

    return render(
        request,
        "users/user_register.html",
        {
            "user": data,
            "editing": True,
            "usuario_id": user_id,
            "persona_id": person.id_persona,
            "edificios": buildings,
            "edificio_actual": current_building,
            "form_errors": form_errors,
        },
    )


@login_required
@admin_required
def user_delete_view(request: HttpRequest, user_id: int) -> HttpResponse:
    user = get_object_or_404(Usuario, id_usuario=user_id)
    person = user.id_persona
    full_name = person.get_full_name() or user.username
    with transaction.atomic():
        person_id = user.id_persona_id
        user.delete()
        if person_id:
            Persona.objects.filter(id_persona=person_id).delete()
    messages.success(request, f"{full_name} eliminado correctamente.")
    return redirect("user_list")


def check_cedula_uniqueness_view(request: HttpRequest) -> JsonResponse:
    ci = request.GET.get("cedula", "").strip()
    exclude_id = request.GET.get("exclude_id", "").strip()
    exclude_persona_id = int(exclude_id) if exclude_id.isdigit() else None

    if not ci:
        return json_ok({"exists": False})

    error = _validate_unique_ci(ci, exclude_persona_id)
    return json_ok({"exists": bool(error), "error": error})


# ── Email views (moved from events.views) ──────────────────────────────────

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


# ── User PDF Report (moved from reports.views.users) ───────────────────────

@login_required
def user_pdf_view(request: Any) -> HttpResponse:
    try:
        query     = request.GET.get("q", "").strip()
        building_id = request.GET.get("edificio", "").strip()
        estado    = request.GET.get("estado", "").strip()

        usuarios = _filter_users_query(query, building_id, estado, extra_fields=True)

        users = [{"rol": u.rol, **build_user_data(u)} for u in usuarios]

        groups: OrderedDict[str, list[Any]] = OrderedDict()
        for b in users:
            key = b["edificio_nombre"] or "Sin edificio"
            groups.setdefault(key, []).append(b)

        now = dt.datetime.now()
        pdf = _create_report_pdf("Reporte de usuarios")

        filtros: list[str] = []
        if query:
            filtros.append(f"Búsqueda: «{query}»")
        if estado:
            estado_labels = {
                "registrado":    "Registrados",
                "por_registrar": "Pendientes de registro",
            }
            filtros.append(f"Estado: {estado_labels.get(estado, estado)}")

        total_registrados = sum(1 for u in users if u["registered"])
        total_pendientes  = len(users) - total_registrados

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
                    "fill":  (235, 241, 249),
                    "text":  (30, 58, 95),
                },
                {
                    "label": "Registrados",
                    "value": total_registrados,
                    "fill":  (240, 253, 244),
                    "text":  (22, 101, 52),
                },
                {
                    "label": "Pendientes",
                    "value": total_pendientes,
                    "fill":  (255, 251, 235),
                    "text":  (146, 64, 14),
                },
                {
                    "label": "Edificios",
                    "value": len(groups),
                    "fill":  (249, 250, 251),
                    "text":  (55, 65, 81),
                },
            ],
        )

        col_widths  = [28, 32, 32, 70, 28]
        col_headers = ["Cédula", "Nombre", "Apellido", "Correo electrónico", "Estado"]
        col_aligns  = ["C", "L", "L", "L", "C"]

        for building_name, members in groups.items():
            if pdf.get_y() > 240:
                pdf.add_page()

            render_section_divider(pdf, f"{building_name} ({len(members)} usuario(s))")
            render_table_header(pdf, col_widths, col_aligns, col_headers)

            _pdf_font(pdf, "", 9)
            pdf.set_draw_color(10, 10, 10)
            for idx, b in enumerate(members):
                estado_str = "Registrado" if b["registered"] else "Pendiente"

                if b["registered"]:
                    est_fill = (240, 253, 244)
                    est_text = (22, 101, 52)
                else:
                    est_fill = (255, 251, 235)
                    est_text = (146, 64, 14)

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

        return make_pdf_response(pdf, "reporte_usuarios.pdf")

    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain",
            status=500,
        )
    except Exception as e:
        logger_email.warning("User PDF generation failed: %s", e)
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain",
            status=500,
        )
