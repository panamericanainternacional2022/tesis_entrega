import os
import secrets
import string
from typing import Any

from django.contrib.auth.hashers import make_password
from django.core import signing
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest
from django.urls import reverse

from apps.buildings.models import UserBuilding
from apps.core.auth_decorators import ADMIN_ROLES
from apps.history.services.email_templates import build_activation_email_html
from apps.history.services.email_sender import send_email_raw
from apps.users.models import Persona, Usuario

_ACTIVATION_EMAIL_PLAIN = """Estimado/a usuario/a:

Su cuenta ha sido registrada en INES — Sistema inteligente en monitoreo. Para completar el proceso de registro y acceder a todas las funciones de la plataforma, es necesario que establezca su nombre de usuario y contraseña a través del siguiente enlace:

{link}

Este enlace es válido durante las próximas 24 horas. Si usted no ha solicitado este registro, puede ignorar el presente correo sin que ello implique ninguna consecuencia.
"""


def build_user_data(user: Usuario) -> dict[str, Any]:
    person = user.id_persona
    assignments = list(user.building_assignments.all())
    ue = assignments[0] if assignments else None
    building = ue.building if ue else None
    name = user.username
    last_name = ""
    id_number = ""
    email = ""
    if person:
        id_number = person.ci
        parts = [person.first_name, person.middle_name]
        name = " ".join(p for p in parts if p) or user.username
        parts_l = [person.first_last_name, person.second_last_name]
        last_name = " ".join(p for p in parts_l if p)
        email = person.email or ""
    return {
        "id": user.id_usuario,
        "cedula": id_number,
        "nombre": name,
        "last_name": last_name,
        "email": email,
        "username": user.username,
        "edificio_nombre": building.name if building else "",
        "edificio_rif": building.rif if building else "",
        "edificio_direccion": building.address if building else "",
        "registered": user.registered,
    }


def generate_random_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_random_username(first_name: str, last_name: str) -> str:
    first_name = first_name.strip()
    last_name = last_name.strip()
    if not first_name or not last_name:
        raise ValueError("Both first_name and last_name are required.")
    base_username = (
        f"{first_name[0].upper()}{last_name.split()[0].capitalize()}"
    )
    username = base_username
    counter = 1
    while Usuario.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    return username


def send_activation_email(email: str, user_id: int, base_url: str) -> str:
    token = signing.dumps({"user_id": user_id, "email": email})
    link = f"{base_url}{reverse('complete_registration')}?token={token}"

    if not os.environ.get("SMTP_USER") or not os.environ.get("SMTP_PASSWORD"):
        raise RuntimeError(
            "SMTP credentials not configured. Activation link: " + link
        )

    plain_body = _ACTIVATION_EMAIL_PLAIN.format(link=link)
    html_body = build_activation_email_html(link)

    try:
        send_email_raw(
            to_addrs=[email],
            subject="Activación de cuenta en INES",
            html_body=html_body,
            plain_body=plain_body,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to send activation email: {e}") from e
    return link


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


def extract_post_data(request: HttpRequest) -> dict[str, Any]:
    return {
        "primerNombre": request.POST.get("primerNombre", "").strip(),
        "segundoNombre": request.POST.get("segundoNombre", "").strip(),
        "primerApellido": request.POST.get("primerApellido", "").strip(),
        "segundoApellido": request.POST.get("segundoApellido", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "cedula": request.POST.get("cedula", "").strip(),
        "id_edificio": request.POST.get("id_edificio", "").strip(),
    }


def has_required_fields(data: dict[str, Any]) -> bool:
    return bool(
        data.get("primerNombre")
        and data.get("primerApellido")
        and data.get("email")
        and data.get("cedula")
        and data.get("id_edificio")
    )


def build_required_field_errors(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    required = (
        "primerNombre",
        "primerApellido",
        "email",
        "cedula",
        "id_edificio",
    )
    for key in required:
        if not data.get(key):
            errors[key] = "Este campo es obligatorio."
    return errors


def create_user_with_retry(
    first_name: str,
    last_name: str,
    password: str,
    person: Persona,
    max_retries: int = 10,
) -> Usuario:
    for _ in range(max_retries):
        username = build_random_username(first_name, last_name)
        try:
            return Usuario.objects.create(
                username=username,
                password=make_password(password),
                id_persona=person,
                rol="US",
            )
        except IntegrityError:
            continue
    raise ValueError(
        "No se pudo generar un nombre de usuario único tras varios intentos."
    )


def build_edit_initial_data(user: Usuario, person: Persona) -> dict[str, Any]:
    current_ue = UserBuilding.objects.filter(user=user).first()
    current_building = current_ue.building if current_ue else None

    return {
        "primerNombre": person.first_name if person else "",
        "segundoNombre": person.middle_name if person else "",
        "primerApellido": person.first_last_name if person else "",
        "segundoApellido": person.second_last_name if person else "",
        "email": person.email if person else "",
        "cedula": person.ci if person else "",
        "id_edificio": current_building.id if current_building else None,
    }
