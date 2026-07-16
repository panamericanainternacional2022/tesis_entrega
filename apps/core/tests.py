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

    # ── Sensores sin umbrales retornan Normal ───────────────────────────────

    def test_variable_without_thresholds_returns_normal(self):
        risk, color = classify_risk("pump_flow_rate", 99)
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    # ── Sensores de enumeración (elev_door_status) ──────────────────────────

    def test_door_status_open_is_normal_without_fault(self):
        """'open' sin fallo activo es Normal — puerta abierta en parada es esperado."""
        risk, color = classify_risk("elev_door_status", "open")
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    def test_door_status_closing_is_normal(self):
        """'closing' ya no es riesgoso — estado transitorio normal per spec."""
        risk, color = classify_risk("elev_door_status", "closing")
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    def test_door_status_closed_is_normal(self):
        risk, color = classify_risk("elev_door_status", "closed")
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    # ── direction == "higher" ───────────────────────────────────────────────
    # Usando la estructura real: {"direction": "higher", "high": X, "critic": Y}

    def test_higher_below_high_is_normal(self):
        thresholds = {"pump_flow_rate": {"direction": "higher", "high": 15.0, "critic": 20.0}}
        risk, color = classify_risk("pump_flow_rate", 10.0, thresholds)
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    def test_higher_at_high_boundary_is_normal(self):
        thresholds = {"pump_flow_rate": {"direction": "higher", "high": 15.0, "critic": 20.0}}
        risk, color = classify_risk("pump_flow_rate", 15.0, thresholds)
        self.assertEqual(risk, RISK_NORMAL)

    def test_higher_above_high_is_alto(self):
        thresholds = {"pump_flow_rate": {"direction": "higher", "high": 15.0, "critic": 20.0}}
        risk, color = classify_risk("pump_flow_rate", 17.0, thresholds)
        self.assertEqual(risk, RISK_ALTO)
        self.assertEqual(color, "orange")

    def test_higher_above_critic_is_critico(self):
        thresholds = {"pump_flow_rate": {"direction": "higher", "high": 15.0, "critic": 20.0}}
        risk, color = classify_risk("pump_flow_rate", 22.0, thresholds)
        self.assertEqual(risk, RISK_CRITICO)
        self.assertEqual(color, "red")

    def test_flow_zero_is_normal_per_spec(self):
        """spec: pump_flow_rate Normal = 0.0 a 15.0, así que 0 es Normal."""
        thresholds = {"pump_flow_rate": {"direction": "higher", "high": 15.0, "critic": 20.0}}
        risk, color = classify_risk("pump_flow_rate", 0.0, thresholds)
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    # ── direction == "range" ────────────────────────────────────────────────
    # Estructura real: {"direction": "range", "high": lo_normal, "critic": hi_normal,
    #                   "crit_low": lo_critico, "crit_high": hi_critico}

    def test_range_inside_normal_band_is_normal(self):
        """Voltaje 220V dentro del rango normal 210-230 V → Normal."""
        thresholds = {"pump_voltage": {
            "direction": "range", "high": 210.0, "critic": 230.0,
            "crit_low": 198.0, "crit_high": 242.0,
        }}
        risk, color = classify_risk("pump_voltage", 220.0, thresholds)
        self.assertEqual(risk, RISK_NORMAL)
        self.assertEqual(color, "green")

    def test_range_outside_normal_but_inside_critical_is_alto(self):
        """Voltaje 240V fuera de 210-230 pero dentro de 198-242 → Alto."""
        thresholds = {"pump_voltage": {
            "direction": "range", "high": 210.0, "critic": 230.0,
            "crit_low": 198.0, "crit_high": 242.0,
        }}
        risk, color = classify_risk("pump_voltage", 240.0, thresholds)
        self.assertEqual(risk, RISK_ALTO)
        self.assertEqual(color, "orange")

    def test_range_below_crit_low_is_critico(self):
        """Voltaje 195V por debajo del límite crítico 198V → Crítico."""
        thresholds = {"pump_voltage": {
            "direction": "range", "high": 210.0, "critic": 230.0,
            "crit_low": 198.0, "crit_high": 242.0,
        }}
        risk, color = classify_risk("pump_voltage", 195.0, thresholds)
        self.assertEqual(risk, RISK_CRITICO)
        self.assertEqual(color, "red")

    def test_range_above_crit_high_is_critico(self):
        """Voltaje 250V por encima del límite crítico 242V → Crítico."""
        thresholds = {"pump_voltage": {
            "direction": "range", "high": 210.0, "critic": 230.0,
            "crit_low": 198.0, "crit_high": 242.0,
        }}
        risk, color = classify_risk("pump_voltage", 250.0, thresholds)
        self.assertEqual(risk, RISK_CRITICO)
        self.assertEqual(color, "red")

    def test_pressure_zero_is_critico_via_range(self):
        """Presión 0 bar < crit_low 0.5 → Crítico (spec: Crítico < 0.5 bar)."""
        thresholds = {"pump_pressure": {
            "direction": "range", "high": 1.0, "critic": 6.0,
            "crit_low": 0.5, "crit_high": 8.0,
        }}
        risk, color = classify_risk("pump_pressure", 0.0, thresholds)
        self.assertEqual(risk, RISK_CRITICO)
        self.assertEqual(color, "red")

    def test_tank_level_normal(self):
        """Nivel tanque 50% dentro del rango 20-85% → Normal."""
        thresholds = {"pump_tank_level": {
            "direction": "range", "high": 20.0, "critic": 85.0,
            "crit_low": 10.0, "crit_high": 95.0,
        }}
        risk, color = classify_risk("pump_tank_level", 50.0, thresholds)
        self.assertEqual(risk, RISK_NORMAL)

    def test_tank_level_low_is_alto(self):
        """Nivel tanque 15% fuera de 20-85% pero dentro de 10-95% → Alto."""
        thresholds = {"pump_tank_level": {
            "direction": "range", "high": 20.0, "critic": 85.0,
            "crit_low": 10.0, "crit_high": 95.0,
        }}
        risk, color = classify_risk("pump_tank_level", 15.0, thresholds)
        self.assertEqual(risk, RISK_ALTO)

    def test_tank_level_critical_low(self):
        """Nivel tanque 5% por debajo del crítico 10% → Crítico."""
        thresholds = {"pump_tank_level": {
            "direction": "range", "high": 20.0, "critic": 85.0,
            "crit_low": 10.0, "crit_high": 95.0,
        }}
        risk, color = classify_risk("pump_tank_level", 5.0, thresholds)
        self.assertEqual(risk, RISK_CRITICO)
