import time
from unittest.mock import patch

from django.test import TestCase

from apps.users.models import Persona, Usuario
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.physics.pump import _update_pump
from apps.sensors.simulation.physics.elevator import _update_elevator
from apps.core.services.risk_service import classify_risk
from apps.sensors.sensor_config import RISK_CRITICO, RISK_NORMAL


# ---------------------------------------------------------------------------
# Helper: create a fresh simulator pre-seeded with a stable state
# ---------------------------------------------------------------------------
def _make_sim(building, pump=True, elevator=True, tank_level=82.0, pump_on=True):
    eq_types = set()
    if pump:
        eq_types.add("bomba")
    if elevator:
        eq_types.add("elevador")
    sim = BuildingSimulator(
        edificio_id=building.id,
        nombre=building.name,
        equipment_types=eq_types,
        floors=building.floors)
    sim.sensor_data["pump_tank_level"] = tank_level
    sim.sensor_data["pump_voltage"] = 220.0
    sim.pump_on = pump_on
    return sim


class SimulatorPhysicsAndAlertsTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            ci="99999999", first_name="Juan", first_last_name="Perez", email="juanp@example.com"
        )
        self.usuario = Usuario.objects.create(
            username="juanp", password="hashed_password", id_persona=self.persona, rol="US", registered=True
        )
        self.building = Building.objects.create(
            name="Conjunto Junin", rif="J-22222222-2", address="Calle Falsa 123", floors=15
        )
        self.equipment_pump = MonitoringEquipment.objects.create(
            name="Bomba Principal", building=self.building, equipment_type="bomba"
        )
        self.equipment_elev = MonitoringEquipment.objects.create(
            name="Elevador Principal", building=self.building, equipment_type="elevador"
        )
        UserBuilding.objects.create(user=self.usuario, building=self.building)
        self.sim = _make_sim(self.building)
        self.sim.sim_paused = False

    # -----------------------------------------------------------------------
    # 1. Door status risk classification (enum vars always Normal)
    # -----------------------------------------------------------------------
    def test_door_status_alert_logic(self):
        """'open' sin fallo activo es Normal — puerta abierta en parada es esperado.
        'closing' es Normal — estado transitorio per spec."""
        risk, _ = classify_risk("elev_door_status", "open", {})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "open", {},
                                active_faults={"elevator": "door_blocked"})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "open", {},
                                active_faults={"elevator": "pos_sensor_fail"})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "closed", {},
                                active_faults={"elevator": "pos_sensor_fail"})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "closing", {})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "closed", {})
        self.assertEqual(risk, RISK_NORMAL)


    # -----------------------------------------------------------------------
    # 8. Email cooldown per variable
    # -----------------------------------------------------------------------
    @patch("apps.history.alerts.engine.threading.Thread")
    def test_email_cooldown_per_variable(self, mock_thread):
        with patch("apps.history.services.email_sender.get_building_emails") as mock_emails:
            mock_emails.return_value = ["juanp@example.com"]
            self.sim.last_email_sent_time_per_var.clear()
            self.sim.active_alerts.clear()
            from apps.history.alerts.engine import send_alert
            send_alert("motor_stuck", True, "Crítico", "Revisar motor", sim=self.sim)
            self.assertEqual(mock_thread.call_count, 1)
            send_alert("elev_door_status", "open", "Crítico", "Puerta abierta", sim=self.sim)
            self.assertEqual(mock_thread.call_count, 2)
            self.sim.active_alerts.pop("elev_door_status", None)
            send_alert("elev_door_status", "open", "Crítico", "Puerta abierta", sim=self.sim)
            self.assertEqual(mock_thread.call_count, 2)

    # -----------------------------------------------------------------------
    # 9. Dynamic equipment status
    # -----------------------------------------------------------------------
    def test_dynamic_equipment_status(self):
        from apps.sensors.services.payload_service import _fetch_equipment_status
        self.equipment_pump.status = "operativo"
        self.equipment_pump.save()
        pump_s, _ = _fetch_equipment_status(
            django_connected=True, active_edificio_id=self.building.id,
            sim_faults={}, active_alerts={}
        )
        self.assertEqual(pump_s, "operativo")
        pump_s, _ = _fetch_equipment_status(
            django_connected=True, active_edificio_id=self.building.id,
            sim_faults={"pump": "dry_run"}, active_alerts={}
        )
        self.assertEqual(pump_s, "falla")
        self.equipment_pump.refresh_from_db()
        self.assertEqual(self.equipment_pump.status, "falla")

    # =======================================================================
    # NEW TESTS — Float switch, pump ON/OFF, faults, elevator OFF
    # =======================================================================



    # -----------------------------------------------------------------------
    # 21. Elevator OFF → speed = 0, no alerts for stationary door
    # -----------------------------------------------------------------------
    def test_elevator_off_idle_state(self):
        """When elevator_on = False the elevator must be completely idle (speed = 0)."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = False
        sim.sensor_data["elev_speed"] = 2.0
        sim.sensor_data["elev_door_status"] = "closed"
        for _ in range(5):
            _update_elevator(sim)
        self.assertEqual(sim.sensor_data["elev_speed"], 0.0, "Elevator OFF must have speed = 0.")

    # -----------------------------------------------------------------------
    # 22. Elevator fault: motor_stuck → speed 0, alert raised
    # -----------------------------------------------------------------------
    def test_elevator_fault_motor_stuck(self):
        """motor_stuck fault must zero speed."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim._elev_state = "MOVING"
        sim.sim_faults["elevator"] = "motor_stuck"
        sim.sensor_data["elev_speed"] = 1.5
        for _ in range(3):
            _update_elevator(sim)
        self.assertEqual(
            sim.sensor_data.get("elev_speed"), 0.0,
            "motor_stuck fault must stop the elevator.")

    # -----------------------------------------------------------------------
    # 23. Elevator fault: power_outage dynamic phases and deceleration
    # -----------------------------------------------------------------------
    def test_elevator_power_outage_dynamics(self):
        """Power outage must decelerate dynamically, keep doors closed during braking, and open doors on completion."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sensor_data["elev_speed"] = 2.0
        sim.sensor_data["elev_door_status"] = "closed"
        sim.sim_faults["elevator"] = "commercial_power_outage"

        # First tick: BRAKE phase. Declines speed rapidly but does not open doors
        _update_elevator(sim)
        self.assertEqual(sim.sensor_data["elev_door_status"], "closed")
        self.assertLess(sim.sensor_data["elev_speed"], 2.0)

        # Fast forward timer to rescue completion
        sim._elev_power_outage_timer = 5.0
        sim._elev_position_meters = 0.1
        _update_elevator(sim)
        self.assertEqual(sim.sensor_data["elev_door_status"], "open")
        self.assertEqual(sim.sensor_data["elev_speed"], 0.0)

    # -----------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # 29. Injecting fault B after fault A cleans A's physical params
    # -----------------------------------------------------------------------
    def test_fault_params_cleaned_on_new_fault(self):
        """Injecting a new fault type must clear the previous fault's physical params."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        # Inject motor_stuck → torque_factor = 0.0
        sim.sim_faults["elevator"] = "motor_stuck"
        _update_elevator(sim)
        self.assertEqual(sim._elev_motor_torque_factor, 0.0)
        # Now inject door_blocked — old motor_stuck params must be cleared
        sim.sim_faults["elevator"] = "door_blocked"
        _update_elevator(sim)
        self.assertEqual(
            sim._elev_motor_torque_factor, 1.0,
            "torque_factor must be restored to 1.0 after switching from motor_stuck to door_blocked.")
        self.assertTrue(
            sim._elev_door_obstructed,
            "door_obstructed must be True for door_blocked fault.")

    # -----------------------------------------------------------------------
    # 31. Position sensor fail freezes actual position
    # -----------------------------------------------------------------------
    def test_pos_sensor_fail_frozen_actual_position(self):
        """pos_sensor_fail must freeze position at actual value, not at arbitrary 4.3."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        actual_floor = 7
        sim._elev_position_meters = actual_floor * 3.5
        sim.sensor_data["elev_position"] = float(actual_floor)
        sim.sim_faults["elevator"] = "pos_sensor_fail"
        # Elevator is moving (speed > 0) but position sensor should stay frozen
        sim._elev_state = "MOVING"
        sim.sensor_data["elev_speed"] = 2.0
        sim._elev_current_accel = 0.0
        for _ in range(5):
            _update_elevator(sim)
        self.assertEqual(
            sim.sensor_data["elev_position"], float(actual_floor),
            "pos_sensor_fail must freeze position at the actual value when fault was injected.")
