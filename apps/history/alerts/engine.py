from __future__ import annotations

import logging
import threading
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.sensors.simulation.models import BuildingSimulator

from apps.sensors.sensor_config import VAR_NAMES, UNITS, FAULT_NAMES_ES

logger = logging.getLogger(__name__)


def _build_email_subject(fault_name: str, risk_level: str) -> str:
    return f"{fault_name} — Nivel {risk_level}"


def _send_compound_email(
    fault_type: str,
    fault_name: str,
    risk_level: str,
    affected_vars: dict,
    recommended_action: str,
    sim: 'BuildingSimulator',
) -> None:
    from apps.history.services.email_sender import send_email_alert
    from apps.history.services.email_recipients import get_building_emails
    from apps.history.services.email_templates import build_compound_alert_email_html

    edificio_nombre = getattr(sim, "nombre", "") or ""
    edificio_id = getattr(sim, "edificio_id", None)
    subject = _build_email_subject(fault_name, risk_level)
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
        finally:
            from django.db import close_old_connections
            try:
                close_old_connections()
            except Exception:
                pass

    try:
        import eventlet
        eventlet.spawn(_do_send)
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

    from apps.sensors.sensor_config import VALUE_DISPLAY_ES

    # Traducir los valores al español y normalizar nombres de variables
    translated_affected_vars = {}
    for var, info in affected_vars.items():
        t_info = info.copy()
        raw_val = info.get("value")
        if raw_val is not None:
            raw_str = str(raw_val).strip()
            val_str = raw_str.lower()
            if var in VALUE_DISPLAY_ES:
                t_info["value"] = VALUE_DISPLAY_ES[var].get(val_str, raw_str.capitalize())
            else:
                t_info["value"] = raw_val
        translated_affected_vars[var] = t_info

    fault_name = FAULT_NAMES_ES.get(fault_type, fault_type)

    # Usar el texto de alerta especial unificada desde FAULT_ALERT_MESSAGES.
    # Esto garantiza que el campo message.action en la BD, el correo y el PDF
    # usen siempre el texto normalizado correspondiente a la falla.
    from apps.sensors.sensor_config import FAULT_ALERT_MESSAGES
    recommended_action = FAULT_ALERT_MESSAGES.get(
        fault_type,
        f"{fault_name} — Anomalía detectada en múltiples sensores de forma simultánea.",
    )

    from apps.sensors.simulation.constants import LOG_SIM
    if LOG_SIM:
        var_names = ", ".join(translated_affected_vars.keys())
        print(
            f"[SIM] {time.strftime('%H:%M:%S')} COMPOUND ALERT: {fault_name} "
            f"vars=[{var_names}] level={risk_level}"
        )

    _send_compound_email(fault_type, fault_name, risk_level, translated_affected_vars, recommended_action, sim)

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
                "display_name": VAR_NAMES.get(var, var.replace("_", " ").capitalize()),
            }
            for var, info in translated_affected_vars.items()
        ],
        "risk": risk_level,
        "message": recommended_action,
    }
    sim.pending_alerts.append(alert_payload)

    from apps.history.services.history_persistence import save_compound_history_record
    eid = sim.edificio_id if sim else None
    save_compound_history_record(
        fault_type=fault_type,
        affected_vars=translated_affected_vars,
        risk_level=risk_level,
        recommended_action=recommended_action,
        edificio_id=eid,
    )
