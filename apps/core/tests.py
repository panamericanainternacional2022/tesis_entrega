from unittest.mock import Mock
from django.test import TestCase, RequestFactory
from django.http import HttpResponse
from django.urls import reverse
from apps.core.auth_decorators import is_admin_role, login_required, ADMIN_ROLES
from apps.core.services.risk_service import classify_risk
from apps.sensors.sensor_config import RISK_NORMAL, RISK_ALTO, RISK_CRITICO


class IsAdminRoleTests(TestCase):
    def test_admin_roles_return_true(self):
        for rol in ADMIN_ROLES:
            self.assertTrue(is_admin_role(rol))

    def test_non_admin_roles_return_false(self):
        for rol in ("US", "OP", None, ""):
            self.assertFalse(is_admin_role(rol))


class LoginRequiredDecoratorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.mock_view = Mock(return_value=HttpResponse("ok"))
        self.wrapped = login_required(self.mock_view)

    def test_redirects_when_not_logged_in(self):
        request = self.factory.get("/")
        request.session = {}
        response = self.wrapped(request)
        self.assertEqual(response.status_code, 302)
        self.mock_view.assert_not_called()

    def test_calls_view_when_logged_in(self):
        request = self.factory.get("/")
        request.session = {"usuario_id": 1}
        response = self.wrapped(request)
        self.assertEqual(response.status_code, 200)
        self.mock_view.assert_called_once()


class AdminRequiredDecoratorTests(TestCase):
    def test_redirects_when_not_admin(self):
        response = self.client.get(reverse("user_list"))
        self.assertEqual(response.status_code, 302)

    def test_calls_view_when_admin(self):
        from apps.users.models import Persona
        p = Persona.objects.create(ci="12345678", first_name="Admin", first_last_name="U", email="a@a.com")
        from django.contrib.auth.hashers import make_password
        from apps.users.models import Usuario
        Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=p, rol="SA", registered=True)
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})
        response = self.client.get(reverse("user_list"))
        self.assertEqual(response.status_code, 200)


class ClassifyRiskTests(TestCase):

    def test_no_risk_vars_return_normal(self):
        from unittest.mock import patch
        with patch("apps.core.services.risk_service.NO_RISK_VARS", ["elev_position"]):
            risk, color = classify_risk("elev_position", 42)
            self.assertEqual(risk, RISK_NORMAL)
            self.assertEqual(color, "green")

    def test_zero_flow_rate_returns_critico_when_pump_on(self):
        risk, color = classify_risk("pump_flow_rate", 0, pump_on=True)
        self.assertEqual(risk, RISK_CRITICO)
        self.assertEqual(color, "red")

    def test_zero_flow_rate_returns_normal_when_pump_off(self):
        risk, color = classify_risk("pump_flow_rate", 0, pump_on=False)
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    def test_zero_pressure_returns_critico_when_pump_on(self):
        risk, color = classify_risk("pump_pressure", 0, pump_on=True)
        self.assertEqual(risk, RISK_CRITICO)
        self.assertEqual(color, "red")

    def test_zero_pressure_returns_normal_when_pump_off(self):
        risk, color = classify_risk("pump_pressure", 0, pump_on=False)
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    def test_door_status_returns_normal_when_idle_and_no_failures(self):
        risk, color = classify_risk("elev_door_status", "open", speed=0.0)
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    def test_door_status_returns_critico_when_moving(self):
        risk, color = classify_risk("elev_door_status", "open", speed=1.5)
        self.assertEqual(risk, RISK_CRITICO)
        self.assertEqual(color, "red")

    def test_door_status_returns_alto_when_failed_closing(self):
        risk, color = classify_risk("elev_door_status", "closing", speed=0.0)
        self.assertEqual(risk, RISK_ALTO)
        self.assertEqual(color, "orange")

    def test_range_direction(self):
        thresholds = {
            "pump_temperature": {"direction": "range", "low": 20, "high": 80},
        }
        risk, color = classify_risk("pump_temperature", 50, thresholds=thresholds)
        self.assertEqual(risk, RISK_NORMAL)

    def test_range_direction_high(self):
        thresholds = {
            "pump_temperature": {"direction": "range", "low": 20, "high": 80},
        }
        risk, color = classify_risk("pump_temperature", 99, thresholds=thresholds)
        self.assertEqual(risk, RISK_ALTO)

    def test_higher_direction(self):
        thresholds = {
            "pump_flow_rate": {"direction": "higher", "low": 10, "medium": 20, "high": 30},
        }
        test_cases = [
            (5, RISK_NORMAL, "green"),
            (15, RISK_ALTO, "orange"),
            (25, RISK_ALTO, "orange"),
            (35, RISK_CRITICO, "red"),
        ]
        for value, expected_risk, expected_color in test_cases:
            risk, color = classify_risk("pump_flow_rate", value, thresholds=thresholds)
            self.assertEqual(risk, expected_risk, f"pump_flow_rate={value}")
            self.assertEqual(color, expected_color, f"pump_flow_rate={value}")

    def test_lower_direction(self):
        thresholds = {
            "tank_level": {"direction": "lower", "low": 80, "medium": 60, "high": 40},
        }
        test_cases = [
            (90, RISK_NORMAL, "green"),
            (70, RISK_ALTO, "orange"),
            (50, RISK_ALTO, "orange"),
            (30, RISK_CRITICO, "red"),
        ]
        for value, expected_risk, expected_color in test_cases:
            risk, color = classify_risk("tank_level", value, thresholds=thresholds)
            self.assertEqual(risk, expected_risk, f"tank_level={value}")
            self.assertEqual(color, expected_color, f"tank_level={value}")
