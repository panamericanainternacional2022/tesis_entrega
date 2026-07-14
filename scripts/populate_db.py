# ruff: noqa: E402
import sys
import os
import django

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.core.dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django.setup()

import random

from django.contrib.auth.hashers import make_password

from apps.users.models import (
    Persona,
    Usuario,
)
from apps.buildings.models import (
    Building,
    UserBuilding,
    MonitoringEquipment,
)
from apps.thresholds.models import ThresholdConfig
from apps.limits.models import SensorLimitConfig
from apps.sensors.sensor_config import DEFAULT_THRESHOLDS, SENSOR_RANGES
from apps.sensors.models import SensorReading

import datetime


_SENSOR_BASELINES = {
    "pump_flow_rate":   (12.0, 18.0),
    "pump_pressure":    (2.5,  4.5),
    "pump_temperature": (30.0, 55.0),
    "pump_vibration":   (1.0,  4.0),
    "pump_tank_level":  (60.0, 90.0),
    "pump_voltage":     (215.0, 235.0),
    "pump_current":     (5.0,  15.0),
    "pump_water_quality": (70.0, 95.0),
    "elev_speed":       (0.5, 2.0),
    "elev_load":        (200.0, 800.0),
    "elev_temperature": (25.0, 60.0),
    "elev_current":     (5.0, 25.0),
    "elev_vibration":   (0.5, 4.0),
    "elev_voltage":     (210.0, 240.0),
}


def _seed_sensor_readings(building, has_elevator=True):
    from django.utils import timezone

    now = timezone.now()
    days = 7
    readings_per_day = 6
    to_create = []

    for day_offset in range(days):
        day = now - datetime.timedelta(days=(days - 1 - day_offset))
        day_factor = 1.0 + random.uniform(-0.15, 0.15)

        for slot in range(readings_per_day):
            ts = day.replace(
                hour=8 + slot * 2, minute=random.randint(0, 59), second=0, microsecond=0
            )

            for var, (lo, hi) in _SENSOR_BASELINES.items():
                if var.startswith("elev_") and not has_elevator:
                    continue
                base = random.uniform(lo, hi)
                value = round(base * day_factor + random.uniform(-1.0, 1.0), 2)
                to_create.append(SensorReading(
                    building=building, variable=var,
                    value=max(lo * 0.5, min(hi * 1.2, value)),
                    risk="Normal", timestamp=ts,
                ))

    SensorReading.objects.bulk_create(to_create, batch_size=500)
    print(f"  -> {len(to_create)} lecturas creadas para {building.name}")


def populate():
    print("Iniciando limpieza de la base de datos...")

    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE TABLE edificio, equipo_monitoreo, historial, persona, "
            "umbral_config, limite_sensor_config, usuario, usuario_edificio, "
            "lectura_sensor RESTART IDENTITY CASCADE;"
        )

    print("Base de datos limpia y secuencias reiniciadas desde 0.")

    print("Iniciando población de base de datos...")

    print("Creando Personas...")

    def random_ci(num):
        prefix = random.choice(["V-", "E-"])
        return f"{prefix}{num}"

    p1, _ = Persona.objects.get_or_create(
        ci=random_ci(12345678),
        defaults={
            "first_name": "Juan",
            "middle_name": "",
            "first_last_name": "Perez",
            "second_last_name": "",
            "email": "mantillaqed@gmail.com",
        },
    )
    p2, _ = Persona.objects.get_or_create(
        ci=random_ci(87654321),
        defaults={
            "first_name": "Maria",
            "middle_name": "",
            "first_last_name": "Gomez",
            "second_last_name": "",
            "email": "elvistek2012@gmail.com",
        },
    )
    p3, _ = Persona.objects.get_or_create(
        ci=random_ci(44332211),
        defaults={
            "first_name": "David",
            "middle_name": "",
            "first_last_name": "Mantilla",
            "second_last_name": "",
            "email": "mantillaquid@gmail.com",
        },
    )
    p4, _ = Persona.objects.get_or_create(
        ci=random_ci(11223344),
        defaults={
            "first_name": "Admin",
            "middle_name": "",
            "first_last_name": "Admin",
            "second_last_name": "",
            "email": "admin@example.com",
        },
    )

    print("Creando Usuarios...")
    _hashed_pw = make_password("password123")
    u1, _ = Usuario.objects.get_or_create(
        username="juanp",
        defaults={"password": _hashed_pw, "id_persona": p1, "rol": "US", "registered": True},
    )
    u2, _ = Usuario.objects.get_or_create(
        username="mariag",
        defaults={"password": _hashed_pw, "id_persona": p2, "rol": "US", "registered": True},
    )
    u3, _ = Usuario.objects.get_or_create(
        username="davidm",
        defaults={"password": _hashed_pw, "id_persona": p3, "rol": "US", "registered": True},
    )
    u4, _ = Usuario.objects.get_or_create(
        username="admin",
        defaults={"password": _hashed_pw, "id_persona": p4, "rol": "SA", "registered": True},
    )

    print("Creando Edificios...")
    e1, _ = Building.objects.get_or_create(
        rif="J-12345678-9",
        defaults={
            "name": "Conjunto Junin",
            "address": "Centro de la ciudad",
            "floors": 10,
        },
    )
    e2, _ = Building.objects.get_or_create(
        rif="J-98765432-1",
        defaults={
            "name": "Residencia La Campiña",
            "address": "Norte de la ciudad",
            "floors": 15,
        },
    )

    print("Asignando Usuarios a Edificios...")
    UserBuilding.objects.get_or_create(user=u1, building=e1)
    UserBuilding.objects.get_or_create(user=u2, building=e2)
    UserBuilding.objects.get_or_create(user=u3, building=e1)
    UserBuilding.objects.get_or_create(user=u3, building=e2)
    UserBuilding.objects.get_or_create(user=u4, building=e1)
    UserBuilding.objects.get_or_create(user=u4, building=e2)

    print("Creando Equipos de Monitoreo...")
    MonitoringEquipment.objects.get_or_create(
        building=e1, equipment_type=MonitoringEquipment.TYPE_PUMP,
        defaults={"name": "Bomba de agua"},
    )
    MonitoringEquipment.objects.get_or_create(
        building=e1, equipment_type=MonitoringEquipment.TYPE_ELEVATOR,
        defaults={"name": "Elevador"},
    )
    MonitoringEquipment.objects.get_or_create(
        building=e2, equipment_type=MonitoringEquipment.TYPE_PUMP,
        defaults={"name": "Bomba de agua"},
    )

    print("Sembrando umbrales por edificio...")
    for edificio in [e1, e2]:
        for variable, cfg in DEFAULT_THRESHOLDS.items():
            ThresholdConfig.objects.update_or_create(
                building=edificio,
                variable=variable,
                defaults={
                    "direction": cfg.get("direction", "higher"),
                    "high": cfg.get("high", 0),
                    "critic": cfg.get("critic", 0),
                },
            )

    print("Sembrando límites de sensores por edificio...")
    for edificio in [e1, e2]:
        for variable, val_range in SENSOR_RANGES.items():
            SensorLimitConfig.objects.update_or_create(
                building=edificio,
                variable=variable,
                defaults={
                    "max_value": val_range[1],
                },
            )

    print("Generando lecturas de sensores de ejemplo (7 días)...")
    _seed_sensor_readings(e1, has_elevator=True)
    _seed_sensor_readings(e2, has_elevator=False)

    print("¡Población de base de datos completada exitosamente!")


if __name__ == "__main__":
    populate()
