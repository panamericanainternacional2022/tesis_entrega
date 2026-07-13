import logging as _logging_bld
from typing import Any

from django.contrib import messages
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_ok
from apps.buildings.models import Building, MonitoringEquipment
from apps.buildings.services import (
    sync_equipment_for_building, EquipmentConfig)
from apps.buildings.validators import (
    validate_building_form, validate_unique_rif)
from apps.users.validators import normalize_rif
from apps.buildings.shared import (
    extract_building_data,
    extract_equipment_config)
from apps.buildings.pdf_builder import generate_building_report_bytes


@login_required
@admin_required
def building_list_view(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    equipamiento = request.GET.get("equipamiento", "").strip()

    buildings = Building.objects.all().prefetch_related("equipment")

    if equipamiento == "elevador":
        buildings = buildings.filter(equipment__equipment_type="elevador")

    if query:
        buildings = buildings.filter(
            Q(name__icontains=query)
            | Q(rif__icontains=query)
        )

    buildings = buildings.distinct()
    return render(
        request,
        "buildings/building_list.html",
        {
            "buildings": list(buildings),
            "current_equipamiento": equipamiento,
        })


@login_required
@admin_required
def register_building_view(request: HttpRequest) -> HttpResponse:
    building_data = {}
    form_errors = {}
    config = EquipmentConfig()

    if request.method == "POST":
        data = extract_building_data(request)
        if data.get("rif"):
            data["rif"] = normalize_rif(data["rif"])
        building_data = data
        config = extract_equipment_config(request)

        form_errors = validate_building_form({
            "nombreEdificio": data["name"],
            "direccion": data["address"],
            "rif": data["rif"],
            "cantidadPisos": data.get("floors"),
        }, has_elevator=config.has_elevator)
        if form_errors:
            messages.error(request, "Corrija los errores indicados en el formulario.")
        else:
            with transaction.atomic():
                building = Building.objects.create(
                    name=data["name"], rif=data["rif"], address=data["address"],
                    floors=int(data["floors"]))
                sync_equipment_for_building(building, config)
            messages.success(request, "Edificio registrado correctamente.")
            return redirect("building_list")

    return render(
        request,
        "buildings/building_register.html",
        {
            "editing": False,
            "form_errors": form_errors,
            "building": building_data,
            "has_elevator": config.has_elevator,
        })


@login_required
@admin_required
def edit_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    form_errors = {}

    equipment_types = set(building.equipment.values_list("equipment_type", flat=True))
    has_elevator = MonitoringEquipment.TYPE_ELEVATOR in equipment_types

    if request.method == "POST":
        data = extract_building_data(request)
        if data.get("rif"):
            data["rif"] = normalize_rif(data["rif"])

        config = extract_equipment_config(request)
        has_elevator = config.has_elevator

        form_errors = validate_building_form(
            {
                "nombreEdificio": data["name"],
                "direccion": data["address"],
                "rif": data["rif"],
                "cantidadPisos": data.get("floors"),
            },
            exclude_building_id=building.id,
            has_elevator=config.has_elevator)
        if form_errors:
            messages.error(request, "Corrija los errores indicados en el formulario.")
        else:
            with transaction.atomic():
                building.name = data["name"]
                building.address = data["address"]
                building.rif = data["rif"]
                building.floors = int(data["floors"])
                building.save()
                sync_equipment_for_building(building, config)
            messages.success(request, "Edificio actualizado correctamente.")
            return redirect("building_list")

    return render(
        request,
        "buildings/building_register.html",
        {
            "editing": True,
            "building": building,
            "form_errors": form_errors,
            "has_elevator": has_elevator,
        })


@login_required
@admin_required
@require_http_methods(["POST"])
def delete_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    building.delete()
    messages.success(
        request,
        "El edificio y todos sus datos asociados se eliminaron correctamente.")
    return redirect("building_list")


def check_rif_uniqueness_view(request: HttpRequest) -> JsonResponse:
    rif = request.GET.get("rif", "").strip()
    exclude_id = request.GET.get("exclude_id", "").strip()
    exclude_building_id = int(exclude_id) if exclude_id.isdigit() else None

    if not rif:
        return json_ok({"exists": False})

    normalized = normalize_rif(rif)
    try:
        validate_unique_rif(normalized, exclude_building_id)
        exists = False
        error = ""
    except ValidationError as e:
        exists = True
        error = str(e)

    return json_ok({"exists": exists, "error": error})


_logger_bld = _logging_bld.getLogger(__name__)


@login_required
def building_report_pdf_view(request: Any, edificio_id: int) -> HttpResponse:
    try:
        pdf_bytes, filename = generate_building_report_bytes(edificio_id, request=request)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain", status=500)
    except Exception as e:
        _logger_bld.warning("Building report PDF failed: %s", e)
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain", status=500)
