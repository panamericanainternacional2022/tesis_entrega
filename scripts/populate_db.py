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

    print("Creando 20 Personas...")

    _first_names = [
        "Juan", "Maria", "David", "Admin", "Carlos",
        "Ana", "Luis", "Sofia", "Pedro", "Laura",
        "Jorge", "Diana", "Miguel", "Carmen", "Andres",
        "Valentina", "Ricardo", "Isabel", "Fernando", "Monica",
    ]
    _last_names = [
        "Perez", "Gomez", "Mantilla", "Admin", "Lopez",
        "Rodriguez", "Martinez", "Garcia", "Sanchez", "Diaz",
        "Torres", "Ramirez", "Flores", "Morales", "Castillo",
        "Ortiz", "Moreno", "Alvarez", "Romero", "Navarro",
    ]

    def random_ci(num):
        prefix = random.choice(["V-", "E-"])
        return f"{prefix}{num}"

    personas = []
    for i in range(20):
        p, _ = Persona.objects.get_or_create(
            ci=random_ci(10000000 + i),
            defaults={
                "first_name": _first_names[i],
                "middle_name": "",
                "first_last_name": _last_names[i],
                "second_last_name": "",
                "email": f"user{i}@example.com",
            },
        )
        personas.append(p)

    print("Creando 20 Usuarios...")
    _hashed_pw = make_password("password123")
    usuarios = []
    for i in range(20):
        u, _ = Usuario.objects.get_or_create(
            username=f"user{i}",
            defaults={
                "password": _hashed_pw,
                "id_persona": personas[i],
                "rol": "SA" if i == 0 else "US",
                "registered": True,
            },
        )
        usuarios.append(u)

    print("Creando 20 Edificios...")
    _building_names = [
        "Conjunto Junin",
        "Residencia La Campiña",
        "Edificio Central",
        "Torre del Parque",
        "Complejo Aurora",
        "Residencias El Sol",
        "Edificio Mar Azul",
        "Torre Bosque",
        "Conjunto Vista Alegre",
        "Edificio Los Pinos",
        "Residencias del Valle",
        "Torre Cristal",
        "Complejo San Miguel",
        "Edificio Pacifico",
        "Residencias Alameda",
        "Torre Nevada",
        "Conjunto Monteverde",
        "Edificio Horizonte",
        "Residencias Palmar",
        "Torre del Lago",
    ]
    _addresses = [
        "Centro de la ciudad",
        "Norte de la ciudad",
        "Av. Principal, Zona Industrial",
        "Calle 5, Urbanización El Parque",
        "Av. Circunvalación, Sector 3",
        "Calle 10, Las Flores",
        "Av. Libertador, Edif. Azul",
        "Urb. El Bosque, Calle 8",
        "Av. Vista Hermosa, Qta. Alegre",
        "Calle Los Pinos, Urb. Pinar",
        "Av. Del Valle, Res. Valle Verde",
        "Calle Cristal, Torre Oficinas",
        "Av. San Miguel, Centro Comercial",
        "Calle Pacifico, Urb. Oceano",
        "Av. Alameda, Res. Alameda",
        "Calle Nevada, Sector Alta",
        "Urb. Monteverde, Av. Principal",
        "Av. Horizonte, Edif. Horizonte",
        "Calle Palmar, Res. Palmar",
        "Av. Del Lago, Torre Lago",
    ]

    edificios = []
    for i in range(20):
        e, _ = Building.objects.get_or_create(
            rif=f"J-{20000000 + i}-{i}",
            defaults={
                "name": _building_names[i],
                "address": _addresses[i],
                "floors": random.randint(5, 30),
            },
        )
        edificios.append(e)

    print("Asignando Usuarios a Edificios...")
    for u in usuarios:
        assigned = random.sample(edificios, k=random.randint(1, 3))
        for b in assigned:
            UserBuilding.objects.get_or_create(user=u, building=b)

    print("Creando Equipos de Monitoreo...")
    for b in edificios:
        MonitoringEquipment.objects.get_or_create(
            building=b, equipment_type=MonitoringEquipment.TYPE_PUMP,
            defaults={"name": f"Bomba de agua - {b.name}"},
        )
        if random.random() < 0.6:
            MonitoringEquipment.objects.get_or_create(
                building=b, equipment_type=MonitoringEquipment.TYPE_ELEVATOR,
                defaults={"name": f"Elevador - {b.name}"},
            )

    print("Sembrando umbrales por edificio...")
    for edificio in edificios:
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
    for edificio in edificios:
        for variable, val_range in SENSOR_RANGES.items():
            SensorLimitConfig.objects.update_or_create(
                building=edificio,
                variable=variable,
                defaults={
                    "max_value": val_range[1],
                },
            )

    print("Generando lecturas de sensores de ejemplo (7 días)...")
    for i, b in enumerate(edificios):
        _seed_sensor_readings(b, has_elevator=(i % 3 != 0))

    print("¡Población de base de datos completada exitosamente!")


if __name__ == "__main__":
    populate()
