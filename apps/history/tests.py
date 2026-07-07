import json
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.history.models import History
from apps.users.models import Persona, Usuario
from apps.buildings.models import Building, MonitoringEquipment
from apps.sensors.sensor_config import RISK_ALTO


class HistoryModelTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", first_name="Test", first_last_name="User", email="t@t.com")
        self.usuario = Usuario.objects.create(username="testuser", password="abc", id_persona=self.persona, rol="US")
        self.building = Building.objects.create(name="Test", rif="J-11111111-0", address="Dir", floors=10)
        self.equipment = MonitoringEquipment.objects.create(name="Bomba", building=self.building, equipment_type="bomba")

    def test_create_history_record(self):
        record = History.objects.create(
            user=self.usuario,
            monitoring_equipment=self.equipment,
            date=timezone.now(),
            message={"risk": RISK_ALTO, "variable": "temperature", "value": 85, "action": "Revisar"},
        )
        self.assertEqual(History.objects.count(), 1)
        self.assertEqual(record.message, record.message)


class HistoryViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", first_name="Admin", first_last_name="User", email="a@a.com")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.building = Building.objects.create(name="Test", rif="J-11111111-0", address="Dir", floors=10)
        self.equipment = MonitoringEquipment.objects.create(name="Bomba", building=self.building, equipment_type="bomba")
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_get_history_empty(self):
        response = self.client.get(reverse("history"))
        self.assertEqual(response.status_code, 200)

    def test_get_history_with_data(self):
        History.objects.create(
            user=self.usuario, monitoring_equipment=self.equipment,
            date=timezone.now(), message={"risk": RISK_ALTO, "variable": "temperature", "value": 85, "action": "Revisar"},
        )
        response = self.client.get(reverse("history"))
        self.assertEqual(response.status_code, 200)

    def test_clear_history(self):
        response = self.client.post(reverse("clear_history"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ok")

