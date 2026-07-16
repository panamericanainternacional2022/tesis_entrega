from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from typing import Any

from apps.core.constants import MIN_PASSWORD_LENGTH
from apps.core.auth_decorators import login_required
from apps.core.utils import verify_password
from apps.users.models import Usuario


@login_required
def configuration_view(request: HttpRequest) -> HttpResponse:
    user_id = request.session.get("usuario_id")
    if not user_id:
        return redirect("login")
    user = get_object_or_404(Usuario, id_usuario=user_id)
    person = user.id_persona

    if request.method == "POST":
        return _handle_config_post(request, user, person)

    return render(
        request,
        "settings/settings.html",
        {
            "usuario": user,
            "persona": person,
            "form_errors": {},
        },
    )


def _handle_config_post(
    request: HttpRequest, user: Usuario, person: Any,
) -> HttpResponse:
    action = request.POST.get("action", "").strip()
    email = request.POST.get("email", "").strip()
    username = request.POST.get("username", "").strip()
    current_password = request.POST.get("current_password", "")
    new_password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")
    form_errors = {}

    if action == "update_profile":
        if not verify_password(current_password, user.password):
            messages.error(request, "Debes ingresar tu contraseña actual para guardar los cambios.")
            return render(
                request,
                "settings/settings.html",
                {
                    "usuario": user,
                    "persona": person,
                    "form_errors": {},
                },
            )

        if email == person.email and username == user.username:
            messages.error(request, "No se detectaron cambios en los datos del perfil.")
            return render(
                request,
                "settings/settings.html",
                {
                    "usuario": user,
                    "persona": person,
                    "form_errors": {},
                },
            )

        _validate_config_email(email, person, form_errors)
        _validate_config_username(username, form_errors)

        if not form_errors:
            if email:
                person.email = email
            if username:
                user.username = username
            person.save()
            user.save()
            messages.success(request, "Datos de perfil actualizados correctamente.")
            return redirect("configuration")

        messages.error(request, "Corrija los errores indicados en los datos del perfil.")
        return render(
            request,
            "settings/settings.html",
            {
                "usuario": {"username": username},
                "persona": {"email": email},
                "form_errors": form_errors,
            },
        )

    elif action == "change_password":
        if not current_password.strip() or not new_password.strip() or not confirm_password.strip():
            messages.error(request, "Todos los campos de contraseña son obligatorios.")
            return render(
                request,
                "settings/settings.html",
                {
                    "usuario": user,
                    "persona": person,
                    "form_errors": {},
                },
            )

        if not verify_password(current_password, user):
            messages.error(request, "La contraseña actual no es correcta.")
            form_errors["current_password"] = "La contraseña actual no es correcta."
            return render(
                request,
                "settings/settings.html",
                {
                    "usuario": user,
                    "persona": person,
                    "form_errors": form_errors,
                },
            )

        _validate_config_new_password(new_password, confirm_password, form_errors)

        if not form_errors:
            user.password = make_password(new_password)
            user.save()
            messages.success(request, "Contraseña actualizada correctamente.")
            return redirect("configuration")

        messages.error(request, "Corrija los errores indicados en el formulario de contraseña.")
        return render(
            request,
            "settings/settings.html",
            {
                "usuario": user,
                "persona": person,
                "form_errors": form_errors,
            },
        )

    return redirect("configuration")


def _validate_config_email(
    email: str, person: Any, form_errors: dict[str, str],
) -> None:
    from apps.users.validators import _validate_email, _validate_unique_email
    if not email:
        return
    err = _validate_email(email)
    if err:
        form_errors["email"] = err
        return
    err = _validate_unique_email(email, exclude_persona_id=person.id_persona)
    if err:
        form_errors["email_unico"] = err


def _validate_config_username(
    username: str, form_errors: dict[str, str],
) -> None:
    from apps.users.validators import _validate_field, _validate_min_length, _validate_max_length, REGEX_USERNAME
    if not username:
        return
    err = _validate_field(
        username, REGEX_USERNAME,
        "El nombre de usuario solo acepta letras y números, sin espacios.",
    )
    if err:
        form_errors["username"] = err
        return
    err = _validate_min_length(username, 4, "El nombre de usuario")
    if err:
        form_errors["username"] = err
        return
    err = _validate_max_length(username, 20, "El nombre de usuario")
    if err:
        form_errors["username"] = err


def _validate_config_new_password(
    new_password: str, confirm_password: str,
    form_errors: dict[str, str],
) -> None:
    if not new_password:
        return
    if len(new_password) < MIN_PASSWORD_LENGTH:
        form_errors["new_password"] = \
            f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
    elif new_password != confirm_password:
        form_errors["confirm_password"] = \
            "Las contraseñas nuevas no coinciden."

