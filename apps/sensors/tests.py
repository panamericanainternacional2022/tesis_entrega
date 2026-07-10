import time
from unittest.mock import patch

from django.test import TestCase

from apps.users.models import Persona, Usuario
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.physics.pump import (
    _update_pump, _TANK_FULL_THRESHOLD, _TANK_LOW_THRESHOLD,
)
from apps.sensors.simulation.physics.elevator import _update_elevator
from apps.core.services.risk_service import classify_risk
from apps.sensors.sensor_config import RISK_CRITICO, RISK_NORMAL, RISK_ALTO
from apps.sensors.simulation.constants import MAX_DOOR_CLOSE_ATTEMPTS


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
        floors=building.floors,
    )
    sim.sensor_data["tank_level"] = tank_level
    sim.sensor_data["voltage"] = 220.0
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
    # 1. Manual Override / Lock
    # -----------------------------------------------------------------------
    def test_manual_override_lock_duration(self):
        """A locked sensor must not change during the override window."""
        self.sim.sensor_data["voltage"] = 150.0
        self.sim.manual_overrides["voltage"] = time.time() + 90.0
        _update_pump(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 150.0)

    # -----------------------------------------------------------------------
    # 2. Voltage Outage stops flow and pressure
    # -----------------------------------------------------------------------
    def test_voltage_outage_dependency(self):
        """Voltage = 0 → flow, pressure, vibration, current all drop to 0."""
        self.sim.sensor_data["voltage"] = 0.0
        self.sim.manual_overrides["voltage"] = time.time() + 90.0
        for _ in range(5):
            _update_pump(self.sim)
        self.assertEqual(self.sim.sensor_data["flow_rate"], 0.0)
        self.assertEqual(self.sim.sensor_data["pressure"],  0.0)
        self.assertEqual(self.sim.sensor_data["vibration"], 0.0)
        self.assertEqual(self.sim.sensor_data["current"],   0.0)

    # -----------------------------------------------------------------------
    # 3. Low tank triggers starvation behaviour
    # -----------------------------------------------------------------------
    def test_tank_level_low_dependency(self):
        """Tank < 10% → low flow, low pressure, high vibration, high temperature."""
        self.sim.sensor_data["tank_level"] = 5.0
        self.sim.manual_overrides["tank_level"] = time.time() + 90.0
        for _ in range(20):
            _update_pump(self.sim)
        self.assertLessEqual(self.sim.sensor_data["flow_rate"], 2.0)
        self.assertLessEqual(self.sim.sensor_data["pressure"],  1.0)
        self.assertGreaterEqual(self.sim.sensor_data["vibration"],   1.0)
        self.assertGreaterEqual(self.sim.sensor_data["temperature"], 50.0)

    # -----------------------------------------------------------------------
    # 4. Centrifugal pump curve
    # -----------------------------------------------------------------------
    def test_centrifugal_pump_curve(self):
        """At flow = 10 l/s the pump curve should produce ~5.8 bar."""
        self.sim.sensor_data["flow_rate"] = 10.0
        self.sim.manual_overrides["flow_rate"] = time.time() + 90.0
        for _ in range(10):
            _update_pump(self.sim)
        pressure = self.sim.sensor_data["pressure"]
        self.assertAlmostEqual(pressure, 5.8, delta=0.5)

    # -----------------------------------------------------------------------
    # 5. Gradual manual transition
    # -----------------------------------------------------------------------
    def test_gradual_manual_transition(self):
        """Manual target should be reached step-by-step, not in one jump."""
        from apps.sensors.simulation.simulation_engine import update_sensor_data
        self.sim.sensor_data["voltage"] = 220.0
        self.sim.manual_targets["voltage"] = 185.0
        self.sim.manual_overrides["voltage"] = time.time() + 90.0
        update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 205.0)
        update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 190.0)
        update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 185.0)
        for _ in range(3):
            update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 185.0)

    # -----------------------------------------------------------------------
    # 6. Elevator overload opens the door
    # -----------------------------------------------------------------------
    def test_elevator_overload_behavior(self):
        """Overloaded elevator in DOOR_CLOSING must reopen doors."""
        self.sim.elevator_on = True
        self.sim._elev_state = "DOOR_CLOSING"
        self.sim._elev_timer = 0.5
        self.sim.sensor_data["load"] = 1000
        self.sim.manual_overrides["load"] = time.time() + 90.0
        _update_elevator(self.sim)
        self.assertEqual(self.sim._elev_state,                "DOOR_OPENING")
        self.assertEqual(self.sim.sensor_data["door_status"], "open")
        self.assertEqual(self.sim.sensor_data["speed"],       0.0)

    # -----------------------------------------------------------------------
    # 7. Door status risk classification
    # -----------------------------------------------------------------------
    def test_door_status_alert_logic(self):
        """Open door while stationary → Normal; while moving or repeated fails → Critical."""
        risk, _ = classify_risk(
            "door_status", "open", {},
            speed=0.0, door_close_attempts=0, position=0.0,
        )
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk(
            "door_status", "open", {},
            speed=1.0, door_close_attempts=0, position=0.0,
        )
        self.assertEqual(risk, RISK_CRITICO)

        risk, _ = classify_risk(
            "door_status", "open", {},
            speed=0.0, door_close_attempts=MAX_DOOR_CLOSE_ATTEMPTS, position=0.0,
        )
        self.assertEqual(risk, RISK_CRITICO)

        risk, _ = classify_risk(
            "door_status", "closing", {},
            speed=0.0, door_close_attempts=1, position=0.0,
        )
        self.assertEqual(risk, RISK_ALTO)

        risk, _ = classify_risk(
            "door_status", "closing", {},
            speed=0.0, door_close_attempts=2, position=0.0,
        )
        self.assertEqual(risk, RISK_CRITICO)

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
            send_alert("door_status", "open", "Crítico", "Puerta abierta", sim=self.sim)
            self.assertEqual(mock_thread.call_count, 2)
            self.sim.active_alerts.pop("door_status", None)
            send_alert("door_status", "open", "Crítico", "Puerta abierta", sim=self.sim)
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
    # 10. Float switch: full tank (≥ 85%) cuts the pump automatically
    # -----------------------------------------------------------------------
    def test_pump_float_switch_high_cutoff(self):
        """When tank reaches the FULL threshold the float switch must turn the pump off."""
        sim = _make_sim(self.building, tank_level=_TANK_FULL_THRESHOLD + 0.1, pump_on=True)
        # Lock the tank so the threshold is not consumed by the physics step
        sim.manual_overrides["tank_level"] = time.time() + 90.0
        _update_pump(sim)
        self.assertFalse(
            sim.pump_on,
            "Float switch should have turned the pump OFF when tank >= FULL threshold.",
        )

    # -----------------------------------------------------------------------
    # 11. Float switch: low tank (< 80%) starts the pump automatically
    # -----------------------------------------------------------------------
    def test_pump_float_switch_low_trigger(self):
        """When tank drops below the LOW threshold the float switch must turn the pump on."""
        sim = _make_sim(self.building, tank_level=_TANK_LOW_THRESHOLD - 1.0, pump_on=False)
        sim.manual_overrides["tank_level"] = time.time() + 90.0
        _update_pump(sim)
        self.assertTrue(
            sim.pump_on,
            "Float switch should have turned the pump ON when tank < LOW threshold.",
        )

    # -----------------------------------------------------------------------
    # 12. Float switch is disabled during manual override window
    # -----------------------------------------------------------------------
    def test_float_switch_respects_manual_override(self):
        """A 90-second manual override must prevent the float switch from acting."""
        sim = _make_sim(self.building, tank_level=_TANK_LOW_THRESHOLD - 1.0, pump_on=False)
        sim.manual_overrides["tank_level"] = time.time() + 90.0
        # Register the manual override that blocks the float switch
        sim.manual_pump_override = True
        _update_pump(sim)
        self.assertFalse(
            sim.pump_on,
            "Float switch must NOT override a user's manual pump-off during the 90-second lock.",
        )

    # -----------------------------------------------------------------------
    # 13. Pump OFF → flow and pressure are exactly 0.0
    # -----------------------------------------------------------------------
    def test_pump_off_idle_sensors(self):
        """When pump_on is False all hydraulic outputs must be 0."""
        sim = _make_sim(self.building, tank_level=50.0, pump_on=False)
        # Pre-seed non-zero values so the test is meaningful
        sim.sensor_data["flow_rate"] = 15.0
        sim.sensor_data["pressure"]  = 5.0
        sim.sensor_data["vibration"] = 2.0
        sim.sensor_data["current"]   = 3.0
        # Lock tank so float switch sees 50% and doesn't turn pump on
        sim.manual_overrides["tank_level"] = time.time() + 90.0
        sim.manual_pump_override = True
        # Progressive idle decay: flow -3.0/tick, pressure -1.5/tick, etc.
        for _ in range(10):
            _update_pump(sim)
        self.assertEqual(sim.sensor_data["flow_rate"], 0.0, "flow_rate must be 0 when pump is OFF.")
        self.assertEqual(sim.sensor_data["pressure"],  0.0, "pressure must be 0 when pump is OFF.")
        self.assertEqual(sim.sensor_data["vibration"], 0.0, "vibration must be 0 when pump is OFF.")
        self.assertEqual(sim.sensor_data["current"],   0.0, "current must be 0 when pump is OFF.")

    # -----------------------------------------------------------------------
    # 14. Pump ON → flow and pressure are above 0.0 under normal conditions
    # -----------------------------------------------------------------------
    def test_pump_on_normal_sensors(self):
        """When pump is ON with a healthy tank, flow and pressure must be positive."""
        sim = _make_sim(self.building, tank_level=82.0, pump_on=True)
        sim.manual_overrides["tank_level"] = time.time() + 90.0
        sim.manual_pump_override = True
        _update_pump(sim)
        self.assertGreater(sim.sensor_data["flow_rate"], 0.0, "flow_rate must be > 0 when pump is ON.")
        self.assertGreater(sim.sensor_data["pressure"],  0.0, "pressure must be > 0 when pump is ON.")

    # -----------------------------------------------------------------------
    # 15. Tank fills when pump is on (inflow > outflow scenario)
    # -----------------------------------------------------------------------
    def test_tank_fills_when_pump_running(self):
        """With pump ON and low flow demand, tank level should eventually increase."""
        sim = _make_sim(self.building, tank_level=50.0, pump_on=True)
        # Force a high flow rate so inflow > building demand
        sim.sensor_data["flow_rate"] = 20.0
        sim.manual_overrides["flow_rate"] = time.time() + 90.0
        sim.manual_pump_override = True
        initial_tank = sim.sensor_data["tank_level"]
        for _ in range(10):
            _update_pump(sim)
        self.assertGreater(
            sim.sensor_data["tank_level"], initial_tank,
            "Tank should fill up when pump flow_rate exceeds building demand.",
        )

    # -----------------------------------------------------------------------
    # 16. Tank drains when pump is off
    # -----------------------------------------------------------------------
    def test_tank_frozen_when_pump_off(self):
        """With pump OFF, the tank level must be frozen (no inflow, no outflow)."""
        sim = _make_sim(self.building, tank_level=70.0, pump_on=False)
        sim.manual_pump_override = True
        sim.sensor_data["tank_level"] = 70.0
        for _ in range(20):
            _update_pump(sim)
        self.assertEqual(
            sim.sensor_data["tank_level"], 70.0,
            "Tank must be frozen when pump is OFF.",
        )

    # -----------------------------------------------------------------------
    # 17. Fault: dry_run → flow drops to 0, temperature rises, tank level drops
    # -----------------------------------------------------------------------
    def test_fault_dry_run_effect(self):
        """dry_run fault must reduce flow to ~0, raise temperature and drain tank."""
        sim = _make_sim(self.building, tank_level=8.0, pump_on=True)
        sim.sim_faults["pump"] = "dry_run"
        sim.sensor_data["tank_level"] = 8.0
        sim.manual_pump_override = True
        initial_temp  = sim.sensor_data["temperature"]
        initial_tank  = sim.sensor_data["tank_level"]
        for _ in range(5):
            _update_pump(sim)
        self.assertLessEqual(sim.sensor_data["flow_rate"], 5.0, "dry_run must reduce flow.")
        self.assertGreaterEqual(sim.sensor_data["temperature"], initial_temp, "dry_run must raise temperature.")
        self.assertLessEqual(sim.sensor_data["tank_level"], initial_tank, "dry_run must drain the tank.")

    # -----------------------------------------------------------------------
    # 18. Fault: pipe_burst → abnormally high flow, pressure drops, tank drains
    # -----------------------------------------------------------------------
    def test_fault_pipe_burst_effect(self):
        """pipe_burst fault must spike flow, drop pressure and drain tank."""
        sim = _make_sim(self.building, tank_level=60.0, pump_on=True)
        sim.sim_faults["pump"] = "pipe_burst"
        sim.sensor_data["flow_rate"] = 10.0
        sim.sensor_data["pressure"]  = 4.0
        sim.manual_pump_override = True
        initial_flow    = sim.sensor_data["flow_rate"]
        initial_tank    = sim.sensor_data["tank_level"]
        for _ in range(5):
            _update_pump(sim)
        self.assertGreater(sim.sensor_data["flow_rate"], initial_flow, "pipe_burst must increase flow.")
        self.assertLess(sim.sensor_data["tank_level"], initial_tank, "pipe_burst must drain tank.")

    # -----------------------------------------------------------------------
    # 19. Fault: power_outage → all electrical and hydraulic values drop to 0
    # -----------------------------------------------------------------------
    def test_fault_power_outage_effect(self):
        """power_outage must zero out flow, pressure, current and collapse voltage."""
        sim = _make_sim(self.building, tank_level=60.0, pump_on=True)
        sim.sim_faults["pump"] = "power_outage"
        sim.sensor_data["voltage"] = 220.0
        sim.manual_pump_override = True
        for _ in range(10):
            _update_pump(sim)
        self.assertEqual(sim.sensor_data["flow_rate"], 0.0, "power_outage must zero flow.")
        self.assertEqual(sim.sensor_data["pressure"],  0.0, "power_outage must zero pressure.")
        self.assertEqual(sim.sensor_data["current"],   0.0, "power_outage must zero current.")
        self.assertLess(sim.sensor_data["voltage"], 50.0,   "power_outage must collapse voltage.")

    # -----------------------------------------------------------------------
    # 20. Fault: tank_level manually set to 10% → sensors respond
    # -----------------------------------------------------------------------
    def test_manual_fault_low_tank_activates_sensors(self):
        """Manual fault: tank_level = 9% with pump ON must trigger starvation mode."""
        sim = _make_sim(self.building, tank_level=9.0, pump_on=True)
        sim.sensor_data["tank_level"] = 9.0  # strictly < 10.0 → starvation
        sim.manual_overrides["tank_level"] = time.time() + 90.0
        sim.manual_pump_override = True
        # Pre-seed values above the expected starvation ceiling
        sim.sensor_data["flow_rate"] = 15.0
        sim.sensor_data["pressure"]  = 5.0
        sim.sensor_data["vibration"] = 0.5
        for _ in range(5):
            _update_pump(sim)
        self.assertLessEqual(sim.sensor_data["flow_rate"],  2.0,  "Low tank must reduce flow.")
        self.assertLessEqual(sim.sensor_data["pressure"],   1.5,  "Low tank must reduce pressure.")
        self.assertGreaterEqual(sim.sensor_data["vibration"], 0.5, "Low tank must keep vibration elevated.")

    # -----------------------------------------------------------------------
    # 21. Elevator OFF → speed = 0, no alerts for stationary door
    # -----------------------------------------------------------------------
    def test_elevator_off_idle_state(self):
        """When elevator_on = False the elevator must be completely idle (speed = 0)."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = False
        sim.sensor_data["speed"] = 2.0       # pre-seed a non-zero speed
        sim.sensor_data["door_status"] = "closed"
        # Progressive idle decay: speed -1.0/tick
        for _ in range(5):
            _update_elevator(sim)
        self.assertEqual(sim.sensor_data["speed"], 0.0, "Elevator OFF must have speed = 0.")

    # -----------------------------------------------------------------------
    # 22. Elevator fault: motor_stuck → speed 0, alert raised
    # -----------------------------------------------------------------------
    def test_elevator_fault_motor_stuck(self):
        """motor_stuck fault must zero speed."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim._elev_state = "MOVING"
        sim.sim_faults["elevator"] = "motor_stuck"
        sim.sensor_data["speed"] = 1.5
        for _ in range(3):
            _update_elevator(sim)
        self.assertEqual(
            sim.sensor_data.get("speed"), 0.0,
            "motor_stuck fault must stop the elevator.",
        )

    # -----------------------------------------------------------------------
    # 23. Elevator fault: power_outage dynamic phases and deceleration
    # -----------------------------------------------------------------------
    def test_elevator_power_outage_dynamics(self):
        """Power outage must decelerate dynamically, keep doors closed during braking, and open doors on completion."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sensor_data["speed"] = 2.0
        sim.sensor_data["door_status"] = "closed"
        sim.sim_faults["elevator"] = "commercial_power_outage"
        
        # First tick: BRAKE phase. Declines speed rapidly but does not open doors
        _update_elevator(sim)
        self.assertEqual(sim.sensor_data["door_status"], "closed")
        self.assertLess(sim.sensor_data["speed"], 2.0)
        
        # Fast forward timer to rescue completion
        sim._elev_power_outage_timer = 5.0
        # Position is near 0
        sim._elev_position_meters = 0.1
        _update_elevator(sim)
        self.assertEqual(sim.sensor_data["door_status"], "open")
        self.assertEqual(sim.sensor_data["speed"], 0.0)

    # -----------------------------------------------------------------------
    # 24. Selective clear_fault resolves only target variables overrides
    # -----------------------------------------------------------------------
    def test_elevator_selective_clear_fault(self):
        """clear_fault must only pop overrides targeted by the active fault, preserving others."""
        from apps.sensors.simulation.controls import clear_fault, inject_fault
        sim = _make_sim(self.building, pump=True, elevator=True)
        from apps.sensors.simulation.globals import simulators
        simulators[self.building.id] = sim
        
        # User sets a manual override on load
        sim.manual_overrides["load"] = time.time() + 90.0
        sim.manual_targets["load"] = 400.0
        
        # Inject pos_sensor_fail (affects speed, position, door_status)
        inject_fault(self.building.id, "elevator", "pos_sensor_fail")
        sim.manual_overrides["position"] = time.time() + 90.0
        sim.manual_targets["position"] = 3.0
        
        # Clear the fault
        clear_fault(self.building.id, "elevator")
        
        # Override on position must be gone
        self.assertNotIn("position", sim.manual_overrides)
        # Override on load must STILL be there
        self.assertIn("load", sim.manual_overrides)
        self.assertEqual(sim.manual_targets["load"], 400.0)

    # -----------------------------------------------------------------------
    # 25. door_close_attempts protection with overrides
    # -----------------------------------------------------------------------
    def test_door_close_attempts_override_protection(self):
        """door_close_attempts must respect manual overrides and not be cleared or updated."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sensor_data["door_close_attempts"] = 5
        sim.door_close_attempts = 5
        sim.manual_overrides["door_close_attempts"] = time.time() + 90.0
        sim.manual_targets["door_close_attempts"] = 5
        
        # Elevator starts moving (spd != 0 normally resets attempts to 0)
        sim._elev_state = "MOVING"
        sim.sensor_data["speed"] = 1.0
        _update_elevator(sim)
        self.assertEqual(sim.sensor_data["door_close_attempts"], 5)
        self.assertEqual(sim.door_close_attempts, 5)

    # -----------------------------------------------------------------------
    # 26. Trip count must NOT increment during motor_stuck fault
    # -----------------------------------------------------------------------
    def test_trip_count_not_incremented_during_motor_stuck(self):
        """motor_stuck fault must NOT increment trip_count despite FSM cycling."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sim_faults["elevator"] = "motor_stuck"
        sim.sensor_data["trip_count"] = 42
        sim._elev_state = "ACCELERATING"
        sim.sensor_data["speed"] = 1.0
        sim._elev_position_meters = 50.0
        for _ in range(10):
            _update_elevator(sim)
        self.assertEqual(
            sim.sensor_data["trip_count"], 42,
            "trip_count must NOT change during motor_stuck fault.",
        )

    # -----------------------------------------------------------------------
    # 27. Trip count must NOT increment during pos_sensor_fail
    # -----------------------------------------------------------------------
    def test_trip_count_not_incremented_during_pos_sensor_fail(self):
        """pos_sensor_fail + emergency stop must NOT increment trip_count."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sim_faults["elevator"] = "pos_sensor_fail"
        sim.sensor_data["trip_count"] = 10
        sim._elev_state = "MOVING"
        sim.sensor_data["speed"] = 2.0
        sim._elev_position_meters = 30.0
        sim._elev_current_accel = 0.0
        # Run enough ticks for mismatch timer (4s) to trigger emergency stop
        for _ in range(8):
            _update_elevator(sim)
        self.assertEqual(
            sim.sensor_data["trip_count"], 10,
            "trip_count must NOT change during pos_sensor_fail emergency stop.",
        )

    # -----------------------------------------------------------------------
    # 28. Trip count must NOT increment during power outage
    # -----------------------------------------------------------------------
    def test_trip_count_not_incremented_during_power_outage(self):
        """commercial_power_outage + battery rescue must NOT increment trip_count."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sim_faults["elevator"] = "commercial_power_outage"
        sim.sensor_data["trip_count"] = 5
        sim._elev_state = "MOVING"
        sim.sensor_data["speed"] = 2.0
        sim._elev_position_meters = 50.0
        sim._elev_current_accel = 0.0
        for _ in range(20):
            _update_elevator(sim)
        self.assertEqual(
            sim.sensor_data["trip_count"], 5,
            "trip_count must NOT change during power outage.",
        )

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
            "torque_factor must be restored to 1.0 after switching from motor_stuck to door_blocked.",
        )
        self.assertTrue(
            sim._elev_door_obstructed,
            "door_obstructed must be True for door_blocked fault.",
        )

    # -----------------------------------------------------------------------
    # 30. Door blocked shows elevated energy consumption
    # -----------------------------------------------------------------------
    def test_door_blocked_elevated_energy(self):
        """door_blocked fault must show elevated energy (door motor cycling)."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sim_faults["elevator"] = "door_blocked"
        sim._elev_state = "DOOR_CLOSING"
        sim.sensor_data["speed"] = 0.0
        for _ in range(5):
            _update_elevator(sim)
        self.assertGreater(
            sim.sensor_data["energy"], 0.8,
            "door_blocked must show elevated energy > 0.8 kW.",
        )

    # -----------------------------------------------------------------------
    # 31. Position sensor fail freezes actual position (not hardcoded 4.3)
    # -----------------------------------------------------------------------
    def test_pos_sensor_fail_frozen_actual_position(self):
        """pos_sensor_fail must freeze position at actual value, not at arbitrary 4.3."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        actual_floor = 7
        sim._elev_position_meters = actual_floor * 3.5
        sim.sensor_data["position"] = float(actual_floor)
        sim.sim_faults["elevator"] = "pos_sensor_fail"
        # Elevator is moving (speed > 0) but position sensor should stay frozen
        sim._elev_state = "MOVING"
        sim.sensor_data["speed"] = 2.0
        sim._elev_current_accel = 0.0
        for _ in range(5):
            _update_elevator(sim)
        self.assertEqual(
            sim.sensor_data["position"], float(actual_floor),
            "pos_sensor_fail must freeze position at the actual value when fault was injected.",
        )


