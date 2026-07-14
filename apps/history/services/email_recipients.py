import logging
from typing import List, Optional

from apps.core.auth_decorators import ADMIN_ROLES


logger = logging.getLogger(__name__)


def get_unit(variable: str) -> str:
    from apps.sensors.sensor_config import UNITS
    return UNITS.get(variable, "")


def get_building_emails(edificio_id: Optional[int] = None) -> List[str]:
    try:
        from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
    except Exception:
        return []
    try:
        if edificio_id is None:
            equipo = MonitoringEquipment.objects.first()
            if equipo and equipo.building:
                edificio_id = equipo.building.id
            else:
                first_edf = Building.objects.first()
                if first_edf:
                    edificio_id = first_edf.id
                else:
                    return []
            logger.warning(
                "get_building_emails llamado sin edificio_id — usando fallback edificio %s. "
                "Los eventos del simulador deberían pasar siempre un edificio_id explícito.",
                edificio_id,
            )

        users = UserBuilding.objects.filter(
            building_id=edificio_id,
            user__registered=True,
        ).exclude(
            user__rol__in=ADMIN_ROLES,
        ).select_related("user__id_persona")
        emails: List[str] = []
        for u in users:
            if u.user and u.user.id_persona and u.user.id_persona.email:
                email = u.user.id_persona.email.strip()
                if email and email not in emails:
                    emails.append(email)
        return emails
    except Exception as e:
        logger.error("Error retrieving emails for building %s: %s", edificio_id, e)
        return []
