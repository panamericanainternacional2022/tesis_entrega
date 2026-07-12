from __future__ import annotations

import logging
import threading
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.sensors.simulation.models import BuildingSimulator

from apps.sensors.sensor_config import RISK_CRITICO, RISK_ALTO, VAR_NAMES, COOLDOWN_SECONDS, UNITS, FAULT_NAMES_ES

logger = logging.getLogger(__name__)


def _translate_variable(variable: str) -> str:
    return VAR_NAMES.get(variable, variable.replace("_", " ").title())


def _build_alert_email_subject(variable: str, risk_level: str) -> str:
    var_display = _translate_variable(variable)
    return f"Alerta de monitoreo: {var_display} — Nivel {risk_level}"


def _build_alert_email_body(
    variable: str, value: float, risk_level: str, recommended_action: str,
    edificio_nombre: str = "",
) -> str:
    from apps.history.services.email_sender import build_standard_email_body, get_unit
    var_display = _translate_variable(variable)
    timestamp = time.strftime("%d/%m/%Y %H:%M:%S")
    unit = get_unit(variable)
    detalles = {
        "Fecha y hora":    timestamp,
        "Edificio":        edificio_nombre or "INES — Sistema inteligente en monitoreo",
        "Parámetro":       var_display,
        "Lectura":         f"{value} {unit}".strip(),
        "Nivel de riesgo": risk_level,
    }
    return build_standard_email_body(
        titulo="Anomalía detectada en los sensores de infraestructura",
        contexto=(
            "El sistema ha registrado una lectura fuera de los rangos operativos "
            "establecidos para el presente edificio. A continuación se detallan "
            "los parámetros del evento y la medida correctiva recomendada."
        ),
        detalles=detalles,
        accion=recommended_action,
    )


def _send_alert_email(
    variable: str,
    value: float,
    risk_level: str,
    recommended_action: str,
    sim: Optional['BuildingSimulator'],
) -> None:
    from apps.history.services.email_sender import send_email_alert, get_building_emails

    if sim is None:
        return
    if risk_level not in (RISK_ALTO, RISK_CRITICO):
        return

    now = time.time()
    if not isinstance(sim.last_email_sent_time_per_var, dict):
        sim.last_email_sent_time_per_var = {}

    last_sent = sim.last_email_sent_time_per_var.get(variable, 0.0)
    if now - last_sent <= COOLDOWN_SECONDS:
        return

    sim.last_email_sent_time_per_var[variable] = now

    edificio_nombre = getattr(sim, "nombre", "") or ""
    edificio_id = getattr(sim, "edificio_id", None)
    subject = _build_alert_email_subject(variable, risk_level)
    body = _build_alert_email_body(
        variable, value, risk_level, recommended_action, edificio_nombre
    )
    recipients = get_building_emails(edificio_id)
    if not recipients:
        logger.info(
            "Sin destinatarios para alerta del edificio %s (variable=%s, nivel=%s)",
            edificio_id, variable, risk_level,
        )
        return

    def _do_send() -> None:
        try:
            send_email_alert(risk_level, subject, body, recipients=recipients)
        except Exception:
            logger.exception(
                "Error enviando email de alerta (variable=%s, nivel=%s)", variable, risk_level
            )

    try:
        threading.Thread(target=_do_send, daemon=True).start()
    except Exception:
        logger.exception("No se pudo iniciar thread de email para alerta %s", variable)


def send_alert(
    variable: str,
    value: float,
    risk_level: str,
    recommended_action: str,
    sim: Optional['BuildingSimulator'] = None,
) -> None:
    if sim is None:
        return

    if variable in sim.active_alerts and sim.active_alerts[variable] == risk_level:
        return
    sim.active_alerts[variable] = risk_level

    from apps.sensors.simulation.constants import LOG_SIM
    if LOG_SIM:
        print(
            f"[SIM] {time.strftime('%H:%M:%S')} ALERT: {variable}={value} level={risk_level}"
        )

    _send_alert_email(variable, value, risk_level, recommended_action, sim)

    alert_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "variable": variable,
        "value": value,
        "risk": risk_level,
        "message": recommended_action,
    }
    sim.pending_alerts.append(alert_payload)

    from apps.history.services.history_persistence import save_history_record
    eid = sim.edificio_id if sim else None
    save_history_record(variable, value, risk_level, recommended_action, edificio_id=eid)


def _build_compound_email_subject(fault_name: str, risk_level: str) -> str:
    return f"Alerta de falla: {fault_name} — Nivel {risk_level}"


def _send_compound_email(
    fault_type: str,
    fault_name: str,
    risk_level: str,
    affected_vars: dict,
    recommended_action: str,
    sim: 'BuildingSimulator',
) -> None:
    from apps.history.services.email_sender import send_email_alert, get_building_emails, build_compound_alert_email_html

    now = time.time()
    if not isinstance(sim.last_email_sent_time_per_var, dict):
        sim.last_email_sent_time_per_var = {}

    # FIX-7 (BRECHA-8): Use raw fault_type key so clear_fault() can reliably
    # remove the cooldown entry regardless of Spanish translation availability.
    fault_key = f"fault_raw:{fault_type}"
    last_sent = sim.last_email_sent_time_per_var.get(fault_key, 0.0)
    if now - last_sent <= COOLDOWN_SECONDS:
        return

    sim.last_email_sent_time_per_var[fault_key] = now

    edificio_nombre = getattr(sim, "nombre", "") or ""
    edificio_id = getattr(sim, "edificio_id", None)
    subject = _build_compound_email_subject(fault_name, risk_level)
    body = build_compound_alert_email_html(
        fault_name=fault_name,
        risk_level=risk_level,
        affected_vars=affected_vars,
        action=recommended_action,
        building_name=edificio_nombre,
    )
    recipients = get_building_emails(edificio_id)
    if not recipients:
        logger.info(
            "Sin destinatarios para alerta compuesta del edificio %s (falla=%s, nivel=%s)",
            edificio_id, fault_name, risk_level,
        )
        return

    def _do_send() -> None:
        try:
            send_email_alert(risk_level, subject, body, recipients=recipients)
        except Exception:
            logger.exception(
                "Error enviando email de alerta compuesta (falla=%s, nivel=%s)", fault_name, risk_level
            )

    try:
        threading.Thread(target=_do_send, daemon=True).start()
    except Exception:
        logger.exception("No se pudo iniciar thread de email para alerta compuesta %s", fault_name)


def send_compound_alert(
    fault_type: str,
    affected_vars: dict,
    risk_level: str,
    sim: Optional['BuildingSimulator'] = None,
) -> None:
    if sim is None:
        return

    fault_name = FAULT_NAMES_ES.get(fault_type, fault_type)

    from apps.sensors.services.professional_action import get_professional_action
    primary_var = max(
        affected_vars.items(),
        key=lambda x: 1 if x[1]["risk"] == RISK_CRITICO else 0,
    )
    recommended_action = get_professional_action(primary_var[0], risk_level, primary_var[1]["value"])

    from apps.sensors.simulation.constants import LOG_SIM
    if LOG_SIM:
        var_names = ", ".join(affected_vars.keys())
        print(
            f"[SIM] {time.strftime('%H:%M:%S')} COMPOUND ALERT: {fault_name} "
            f"vars=[{var_names}] level={risk_level}"
        )

    _send_compound_email(fault_type, fault_name, risk_level, affected_vars, recommended_action, sim)

    alert_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "fault_type": fault_type,
        "fault_name": fault_name,
        "variables": [
            {
                "variable": var,
                "value": info["value"],
                "risk": info["risk"],
                "unit": UNITS.get(var, ""),
                "display_name": VAR_NAMES.get(var, var),
            }
            for var, info in affected_vars.items()
        ],
        "risk": risk_level,
        "message": recommended_action,
    }
    sim.pending_alerts.append(alert_payload)

    from apps.history.services.history_persistence import save_compound_history_record
    eid = sim.edificio_id if sim else None
    save_compound_history_record(
        fault_type=fault_type,
        affected_vars=affected_vars,
        risk_level=risk_level,
        recommended_action=recommended_action,
        edificio_id=eid,
    )
