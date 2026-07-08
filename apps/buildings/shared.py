from django.http import HttpRequest

from apps.buildings.services import EquipmentConfig


def pop_messages(request: HttpRequest) -> list:
    return request.session.pop("_bld_msg", [])


def extract_building_data(request: HttpRequest) -> dict:
    return {
        "name": request.POST.get("nombreEdificio", "").strip(),
        "address": request.POST.get("direccion", "").strip(),
        "rif": request.POST.get("rif", "").strip(),
        "floors": request.POST.get("cantidadPisos", "").strip(),
    }


def extract_equipment_config(request: HttpRequest) -> EquipmentConfig:
    return EquipmentConfig(
        has_elevator=request.POST.get("con_elevador") == "true",
    )




