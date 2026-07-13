import re
from typing import Optional

from django.core.exceptions import ValidationError

from apps.buildings.models import Building

REGEX_BUILDING_NAME: re.Pattern = re.compile(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9\s]+$")
MAX_FLOORS = 150


def validate_unique_rif(rif: str, exclude_building_id: Optional[int] = None) -> None:
    if not rif:
        return
    qs = Building.objects.filter(rif=rif)
    if exclude_building_id:
        qs = qs.exclude(id=exclude_building_id)
    if qs.exists():
        raise ValidationError("El RIF ya está registrado en otro edificio.")


def _validate_floors_elevator(floors: str, has_elevator: bool) -> str | None:
    try:
        floors_val = int(floors)
        if has_elevator and floors_val <= 1:
            return "Un edificio de 1 piso no puede tener elevador."
    except (ValueError, TypeError):
        return "La cantidad de pisos debe ser un número entero."
    return None


def validate_building_form(
    data: dict, exclude_building_id: Optional[int] = None
) -> dict[str, str]:
    errors: dict[str, str] = {}

    if not data.get("nombreEdificio"):
        errors["nombreEdificio"] = "Este campo es obligatorio."
    if not data.get("rif"):
        errors["rif"] = "Este campo es obligatorio."
    if not data.get("direccion"):
        errors["direccion"] = "Este campo es obligatorio."
    if not data.get("cantidadPisos"):
        errors["cantidadPisos"] = "Este campo es obligatorio."
    if errors:
        return errors

    from apps.users.validators import (
        REGEX_ADDRESS, _validate_field, _validate_min_length,
        _validate_max_length, _validate_rif,
    )

    error = _validate_field(data.get("nombreEdificio", ""), REGEX_BUILDING_NAME,
                            "El nombre del edificio solo acepta letras y números.")
    if error:
        errors["nombreEdificio"] = error

    error = _validate_min_length(data.get("nombreEdificio", ""), 3, "El nombre del edificio")
    if error:
        errors["nombreEdificio_min"] = error

    error = _validate_max_length(data.get("nombreEdificio", ""), 40, "El nombre del edificio")
    if error:
        errors["nombreEdificio_long"] = error

    error = _validate_field(data.get("direccion", ""), REGEX_ADDRESS,
                            "La dirección contiene caracteres no válidos.")
    if error:
        errors["direccion"] = error

    error = _validate_min_length(data.get("direccion", ""), 8, "La dirección")
    if error:
        errors["direccion_min"] = error

    error = _validate_max_length(data.get("direccion", ""), 100, "La dirección")
    if error:
        errors["direccion_long"] = error

    error = _validate_max_length(data.get("rif", ""), 16, "El RIF")
    if error:
        errors["rif_long"] = error

    error = _validate_rif(data.get("rif", ""))
    if error:
        errors["rif"] = error

    try:
        validate_unique_rif(data.get("rif", ""), exclude_building_id)
    except ValidationError as e:
        errors["rif_unico"] = e.messages[0]

    floors_val = data.get("cantidadPisos")
    if floors_val:
        try:
            val = int(floors_val)
            if val <= 0:
                errors["cantidadPisos"] = "La cantidad de pisos debe ser mayor a 0."
            elif val > MAX_FLOORS:
                errors["cantidadPisos"] = f"La cantidad de pisos no puede exceder {MAX_FLOORS}."
        except (ValueError, TypeError):
            errors["cantidadPisos"] = "La cantidad de pisos debe ser un número entero."

    return errors
