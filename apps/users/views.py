from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.core import signing
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.buildings.models import Building, UserBuilding
from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_ok
from apps.users.models import Usuario, Persona
from apps.users.services import (
    build_user_data,
    generate_random_password,
    send_activation_email,
    extract_post_data,
    has_required_fields,
    build_required_field_errors,
    create_user_with_retry,
    build_edit_initial_data,
    _filter_users_query,
)
from apps.users.validators import validate_user_form, _validate_unique_ci


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

    building_name = ""
    if building_id.isdigit():
        b = Building.objects.filter(id=building_id).first()
        if b:
            building_name = b.name

    estado_display = {"registrado": "Registrados", "por_registrar": "Por registrar"}.get(estado, estado)

    return render(request, "users/user_list.html", {
        "usuarios": users,
        "edificios": buildings,
        "selected_edificio_id": int(building_id) if building_id.isdigit() else None,
        "selected_edificio_nombre": building_name,
        "current_estado": estado,
        "current_estado_display": estado_display,
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

                edificio_id = post_data.get("id_edificio")
                if edificio_id:
                    if not Building.objects.filter(id=edificio_id).exists():
                        messages.error(request, "El edificio seleccionado no existe.")
                        return redirect("user_register")
                    UserBuilding.objects.create(user=created_user, building_id=edificio_id)

                try:
                    activation_link = send_activation_email(
                        post_data["email"], created_user.id_usuario,
                        f"{'https' if request.is_secure() else 'http'}://{request.get_host()}",
                    )
                    email_sent = True
                except Exception:
                    token = signing.dumps({"user_id": created_user.id_usuario, "email": post_data["email"]})
                    activation_link = f"{'https' if request.is_secure() else 'http'}://{request.get_host()}{reverse('complete_registration')}?token={token}"

                if email_sent:
                    messages.success(request, f"Se envió el correo de activación a {post_data['email']}.")
                else:
                    messages.warning(request, f"No se pudo enviar el correo; entregue el enlace de activación manualmente: {activation_link}")

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

        if not has_required_fields(post_data, require_building=False):
            messages.error(request, "Complete los campos obligatorios para actualizar: nombre, apellido, correo electrónico y cédula.")
            form_errors = build_required_field_errors(post_data, require_building=False)
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
                # NOTE: Los edificios se gestionan desde la lista de usuarios
                # mediante el modal de vinculación/desvinculación (Opción A).

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

    return render(
        request,
        "users/user_register.html",
        {
            "user": data,
            "editing": True,
            "usuario_id": user_id,
            "persona_id": person.id_persona,
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


@login_required
@admin_required
@require_http_methods(["POST"])
def user_link_building_view(request: HttpRequest, user_id: int) -> JsonResponse:
    """Vincula un edificio adicional a un usuario. Idempotente."""
    from apps.core.services.http_response import json_error
    import json as _json
    try:
        data = _json.loads(request.body)
    except (_json.JSONDecodeError, ValueError):
        return json_error("JSON inválido", status=400)

    building_id = data.get("building_id")
    if not building_id:
        return json_error("building_id requerido", status=400)

    user = get_object_or_404(Usuario, id_usuario=user_id)
    building = get_object_or_404(Building, id=building_id)

    _, created = UserBuilding.objects.get_or_create(user=user, building=building)
    assignments = list(
        UserBuilding.objects.filter(user=user)
        .select_related("building")
        .values("building__id", "building__name")
    )
    edificios = [{"id": a["building__id"], "nombre": a["building__name"]} for a in assignments]
    return json_ok({
        "created": created,
        "edificios": edificios,
    })


@login_required
@admin_required
@require_http_methods(["POST"])
def user_unlink_building_view(request: HttpRequest, user_id: int) -> JsonResponse:
    """Desvincula un edificio de un usuario. Requiere que quede al menos uno."""
    from apps.core.services.http_response import json_error
    import json as _json
    try:
        data = _json.loads(request.body)
    except (_json.JSONDecodeError, ValueError):
        return json_error("JSON inválido", status=400)

    building_id = data.get("building_id")
    if not building_id:
        return json_error("building_id requerido", status=400)

    user = get_object_or_404(Usuario, id_usuario=user_id)
    total = UserBuilding.objects.filter(user=user).count()
    if total <= 1:
        return json_error("El usuario debe tener al menos un edificio asignado.", status=400)

    deleted, _ = UserBuilding.objects.filter(user=user, building_id=building_id).delete()
    if not deleted:
        return json_error("Asignación no encontrada.", status=404)

    assignments = list(
        UserBuilding.objects.filter(user=user)
        .select_related("building")
        .values("building__id", "building__name")
    )
    edificios = [{"id": a["building__id"], "nombre": a["building__name"]} for a in assignments]
    return json_ok({"edificios": edificios})
