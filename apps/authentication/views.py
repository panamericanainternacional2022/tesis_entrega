from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core import signing
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.core.constants import MIN_PASSWORD_LENGTH, MIN_USERNAME_LENGTH, MAX_USERNAME_LENGTH
from apps.core.utils import verify_password
from apps.users.models import Usuario
from apps.users.validators import REGEX_USERNAME

import logging
logger = logging.getLogger(__name__)

ERROR_INVALID_CREDENTIALS = "Usuario o contraseña incorrectos."


def login_view(request: HttpRequest) -> HttpResponse:
    form_error: str | None = None
    form_errors: dict[str, str] = {}
    username_val = request.POST.get("username", "").strip()

    success = None
    storage = messages.get_messages(request)
    for msg in storage:
        if msg.level_tag == "success":
            success = str(msg)
            break

    ip = request.META.get("REMOTE_ADDR", "")
    rate_key = f"login_rate_{ip}"
    attempts = cache.get(rate_key, 0)

    if request.method == "POST":
        if attempts >= 5:
            form_error = "Demasiados intentos. Intenta de nuevo en 1 minuto."
            return render(request, "authentication/login.html", {
                "form_error": form_error,
                "form_errors": form_errors,
                "username_val": username_val,
                "success": None,
            })

        password = request.POST.get("password", "").strip()

        _validate_login_fields(username_val, password, form_errors)

        if not form_errors:
            user = (
                Usuario.objects.select_related("id_persona")
                .filter(username=username_val)
                .first()
            )
            if user and verify_password(password, user):
                cache.delete(rate_key)
                _setup_session(request, user)
                return redirect("monitor")
            form_error = ERROR_INVALID_CREDENTIALS
            cache.set(rate_key, attempts + 1, 60)
            logger.warning("Login fallido para usuario '%s' desde IP %s", username_val, ip)

    return render(request, "authentication/login.html", {
        "form_error": form_error,
        "form_errors": form_errors,
        "username_val": username_val,
        "success": success,
    })


def logout_view(request: HttpRequest) -> HttpResponse:
    request.session.flush()
    return redirect("login")


def complete_registration_view(request: HttpRequest) -> HttpResponse:
    token = request.GET.get("token") or request.POST.get("token")
    if not token:
        return render(
            request,
            "authentication/complete_registration.html",
            {"error": "Token de registro faltante o inválido."},
        )

    user = _resolve_registration_token(token)
    if user is None:
        return render(
            request,
            "authentication/complete_registration.html",
            {"error": "El enlace de registro ha expirado o es inválido."},
        )

    if user.registered:
        return render(
            request,
            "authentication/complete_registration.html",
            {"error": "Este registro ya fue completado anteriormente. Puede iniciar sesión."},
        )

    form_errors: dict[str, str] = {}
    username_val = request.POST.get("username", "").strip()

    if request.method == "POST":
        password = request.POST.get("password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        form_errors = _validate_registration_form(
            username_val, password, confirm_password, user
        )
        if not form_errors:
            user.username = username_val
            user.password = make_password(password)
            user.registered = True
            user.save(update_fields=["username", "password", "registered"])
            messages.success(
                request,
                "Registro completado con éxito. Ahora puede iniciar sesión.",
            )
            return redirect("login")

    return render(
        request,
        "authentication/complete_registration.html",
        {
            "token": token,
            "username_val": username_val,
            "form_error": _first_error(form_errors),
            "form_errors": form_errors,
        },
    )


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def _setup_session(request: HttpRequest, user: Usuario) -> None:
    request.session["usuario_id"] = user.id_usuario
    request.session["usuario_rol"] = user.rol or "US"
    request.session["usuario_es_admin"] = user.rol == "SA"

    person = user.id_persona
    if person:
        name_parts = [person.first_name, person.first_last_name]
        request.session["usuario_nombre_completo"] = " ".join(p for p in name_parts if p)
    else:
        request.session["usuario_nombre_completo"] = user.username


def _resolve_registration_token(token: str) -> Usuario | None:
    try:
        data = signing.loads(token, max_age=settings.TOKEN_MAX_AGE)
        return Usuario.objects.get(id_usuario=data["user_id"])
    except (signing.BadSignature, signing.SignatureExpired, Usuario.DoesNotExist):
        return None


def _validate_login_fields(
    username: str, password: str, errors: dict[str, str]
) -> None:
    if not username:
        errors["username"] = "Este campo es obligatorio."
    elif len(username) > MAX_USERNAME_LENGTH:
        errors["username"] = f"Máximo {MAX_USERNAME_LENGTH} caracteres."
    if not password:
        errors["password"] = "Este campo es obligatorio."


def _validate_registration_form(
    username: str, password: str, confirm_password: str, user: Usuario
) -> dict[str, str]:
    errors: dict[str, str] = {}

    if not username:
        errors["username"] = "Este campo es obligatorio."
    if not password:
        errors["password"] = "Este campo es obligatorio."
    if not confirm_password:
        errors["confirm_password"] = "Este campo es obligatorio."

    if errors:
        return errors

    if password != confirm_password:
        errors["confirm_password"] = "Las contraseñas no coinciden."
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
    elif len(password) > 128:
        errors["password"] = "Máximo 128 caracteres."

    if not REGEX_USERNAME.match(username):
        errors["username"] = "El nombre de usuario solo acepta letras y números."
    elif len(username) < MIN_USERNAME_LENGTH:
        errors["username"] = f"El nombre de usuario debe tener al menos {MIN_USERNAME_LENGTH} caracteres."
    elif len(username) > MAX_USERNAME_LENGTH:
        errors["username"] = f"El nombre de usuario debe tener máximo {MAX_USERNAME_LENGTH} caracteres."
    elif (
        Usuario.objects.filter(username=username)
        .exclude(id_usuario=user.id_usuario)
        .exists()
    ):
        errors["username"] = "El nombre de usuario ya está registrado."

    return errors


def _first_error(errors: dict[str, str]) -> str | None:
    return next(iter(errors.values()), None)
