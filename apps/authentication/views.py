from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.users.models import Usuario
from apps.users.validators import REGEX_USERNAME

ERROR_INVALID_CREDENTIALS = "Usuario o contraseña incorrectos."


def login_view(request: HttpRequest) -> HttpResponse:
    form_errors: dict[str, str] = {}
    username_val = request.POST.get("username", "").strip()

    if request.method == "POST":
        password = request.POST.get("password", "").strip()

        _validate_login_fields(username_val, password, form_errors)

        if not form_errors:
            user = (
                Usuario.objects.select_related("id_persona")
                .filter(username=username_val)
                .first()
            )
            if user and _verify_password(password, user):
                _setup_session(request, user)
                return redirect("monitor")
            form_errors["password"] = ERROR_INVALID_CREDENTIALS

    return render(request, "authentication/login.html", {
        "form_error": _first_error(form_errors),
        "form_errors": form_errors,
        "username_val": username_val,
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
            "usuario": user,
            "token": token,
            "username_val": username_val,
            "form_error": _first_error(form_errors),
            "form_errors": form_errors,
        },
    )


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def _verify_password(raw_password: str, user: Usuario) -> bool:
    if check_password(raw_password, user.password):
        return True
    if user.password == raw_password:
        user.password = make_password(raw_password)
        user.save(update_fields=["password"])
        return True
    return False


def _setup_session(request: HttpRequest, user: Usuario) -> None:
    request.session["usuario_id"] = user.id_usuario
    request.session["usuario_username"] = user.username
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
    elif len(password) < 6:
        errors["password"] = "La contraseña debe tener al menos 6 caracteres."

    if not REGEX_USERNAME.match(username):
        errors["username"] = "El nombre de usuario solo acepta letras y números."
    elif (
        Usuario.objects.filter(username=username)
        .exclude(id_usuario=user.id_usuario)
        .exists()
    ):
        errors["username"] = "El nombre de usuario ya está registrado."

    return errors


def _first_error(errors: dict[str, str]) -> str | None:
    return next(iter(errors.values()), None)
