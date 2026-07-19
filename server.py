#!/usr/bin/env python3
# ruff: noqa: E402
import eventlet
eventlet.monkey_patch()
import eventlet.wsgi
try:
    import eventlet.support.psycopg2_patcher
    eventlet.support.psycopg2_patcher.make_psycopg_green()
except ImportError:
    pass

import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from apps.core.dotenv import load_dotenv
load_dotenv()
logger.info(".env cargado antes de Django setup")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.globals import simulators
from apps.sensors.engine import generate_data_and_emit
from apps.buildings.models import MonitoringEquipment

equipos = MonitoringEquipment.objects.select_related("building").all()
for eq in equipos:
    if not eq.building:
        continue
    eid = eq.building.id
    enombre = eq.building.name or f"Edificio #{eid}"
    if eid not in simulators:
        simulators[eid] = BuildingSimulator(eid, enombre, floors=eq.building.floors)
    simulators[eid].equipment_types.add(eq.equipment_type)
    simulators[eid].has_pump = "bomba" in simulators[eid].equipment_types
    simulators[eid].has_elevator = "elevador" in simulators[eid].equipment_types
    simulators[eid].pump_on = simulators[eid].has_pump
    simulators[eid].elevator_on = simulators[eid].has_elevator
    logger.info("Simulador creado: edificio=%s tipo=%s", eid, eq.equipment_type)

logger.info("Simuladores activos: %s", list(simulators.keys()))

_smtp_user = os.environ.get("SMTP_USER", "")
_smtp_password = os.environ.get("SMTP_PASSWORD", "")
_smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
_smtp_port = int(os.environ.get("SMTP_PORT", 587))
if _smtp_user and _smtp_password:
    try:
        import smtplib
        _test_server = smtplib.SMTP(_smtp_server, _smtp_port, timeout=10)
        _test_server.starttls()
        _test_server.login(_smtp_user, _smtp_password)
        _test_server.quit()
        logger.info("Conexión SMTP verificada correctamente")
    except Exception as e:
        logger.warning("No se pudo conectar con SMTP (%s:%s): %s. Los correos no se enviarán.", _smtp_server, _smtp_port, e)
else:
    logger.warning("SMTP no configurado. Los correos no se enviarán.")

def _engine_watchdog():
    while True:
        logger.info("Loop de simulación iniciado via server.py")
        gt = eventlet.spawn(generate_data_and_emit)
        try:
            gt.wait()
            logger.warning(
                "Loop de simulación terminó normalmente (inesperado) - reintentando"
            )
        except Exception:
            logger.exception(
                "Loop de simulación falló con excepción - reintentando en 5 s"
            )
        eventlet.sleep(5)

eventlet.spawn(_engine_watchdog)
logger.info("Watchdog del simulador iniciado")

from django.core.handlers.wsgi import WSGIHandler
from django.contrib.staticfiles.handlers import StaticFilesHandler

application = StaticFilesHandler(WSGIHandler())
host = os.environ.get("SIM_HOST", "0.0.0.0")
port = int(os.environ.get("SIM_PORT", 8000))

logger.info("Servidor PCLogo unificado en http://%s:%s", host, port)
eventlet.wsgi.server(eventlet.listen((host, port)), application)
