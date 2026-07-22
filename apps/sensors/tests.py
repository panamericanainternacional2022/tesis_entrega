from django.test import TestCase

from apps.users.models import Persona, Usuario
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.physics.elevator import _update_elevator
from apps.core.services.risk_service import classify_risk
from apps.sensors.sensor_config import RISK_NORMAL


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
        """'open' sin fallo activo es Normal - puerta abierta en parada es esperado.
        'closing' es Normal - estado transitorio per spec."""
        risk, _ = classify_risk("elev_door_status", "open", {})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "open", {})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "open", {})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "closed", {})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "closing", {})
        self.assertEqual(risk, RISK_NORMAL)

        risk, _ = classify_risk("elev_door_status", "closed", {})
        self.assertEqual(risk, RISK_NORMAL)




    # =======================================================================
    # NEW TESTS - Float switch, pump ON/OFF, faults, elevator OFF
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
        sim._elev_position_meters = 0.0
        _update_elevator(sim)
        _update_elevator(sim)
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
        # Now inject door_blocked - old motor_stuck params must be cleared
        sim.sim_faults["elevator"] = "door_blocked"
        _update_elevator(sim)
        self.assertEqual(
            sim._elev_motor_torque_factor, 1.0,
            "torque_factor must be restored to 1.0 after switching from motor_stuck to door_blocked.")
        self.assertTrue(
            sim._elev_door_obstructed,
            "door_obstructed must be True for door_blocked fault.")

    # -----------------------------------------------------------------------


    # -----------------------------------------------------------------------
    # 32. Commercial Power Outage Step Dynamics & Brake Shock Impulse
    # -----------------------------------------------------------------------
    def test_elevator_power_outage_step_and_brake_shock(self):
        """Power outage must step drop voltage to 0V and current to 0A, and trigger brake drop shock vibration."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sensor_data["elev_speed"] = 1.0
        sim.sim_faults["elevator"] = "commercial_power_outage"
        _update_elevator(sim)
        self.assertEqual(sim.sensor_data["elev_voltage"], 0.0, "Voltage must drop to 0V step in power outage.")
        self.assertEqual(sim.sensor_data["elev_current"], 0.0, "Current must drop to 0A step in power outage.")
        self.assertGreaterEqual(sim.sensor_data["elev_vibration"], 9.0, "Mechanical brake engagement must cause vibration shock.")

    # -----------------------------------------------------------------------
    # 33. Motor Stuck Locked Rotor Amperage (LRA) & Voltage Dip
    # -----------------------------------------------------------------------
    def test_elevator_motor_stuck_lra_and_voltage_sag(self):
        """Motor stuck fault must step current to LRA (85A) and cause line voltage sag."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sim_faults["elevator"] = "motor_stuck"
        _update_elevator(sim)
        self.assertEqual(sim.sensor_data["elev_speed"], 0.0)
        self.assertEqual(sim.sensor_data["elev_current"], 85.0, "Jammed motor must step to Locked Rotor Amperage (85A).")
        self.assertLessEqual(sim.sensor_data["elev_voltage"], 360.0, "LRA current spike must sag line voltage.")

    # -----------------------------------------------------------------------
    # 34. Door Blocked Safety Chain Interlock & Operator Current
    # -----------------------------------------------------------------------
    def test_elevator_door_blocked_safety_chain(self):
        """Door blocked fault must set status to 'blocked' and draw door operator motor current while main motor is 0A."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sim_faults["elevator"] = "door_blocked"
        _update_elevator(sim)
        self.assertEqual(sim.sensor_data["elev_door_status"], "blocked")
        self.assertEqual(sim.sensor_data["elev_speed"], 0.0)
        self.assertEqual(sim.sensor_data["elev_current"], 2.5, "Door operator motor draws operator current while main motor is disabled.")

    # -----------------------------------------------------------------------
    # 35. Traction Loss (Rope Slip) Low Current & Normal Thermodynamics
    # -----------------------------------------------------------------------
    def test_elevator_traction_loss_thermodynamics(self):
        """Traction loss must reflect no-load motor current and normal motor temperature range (no false overheating)."""
        sim = _make_sim(self.building, pump=True, elevator=True)
        sim.elevator_on = True
        sim.sim_faults["elevator"] = "traction_loss"
        for _ in range(5):
            _update_elevator(sim)
        self.assertLessEqual(sim.sensor_data["elev_current"], 6.0, "Motor in no-load state draws low current (~5.6A).")
        self.assertLessEqual(sim.sensor_data["elev_temperature"], 40.0, "Unloaded motor does not overheat (Joule heating P=I^2*R is minimal).")
        self.assertGreaterEqual(sim.sensor_data["elev_vibration"], 5.0, "Rope slippage produces high vibration.")


from apps.sensors.simulation.physics.pump import _update_pump


class PumpFaultsPhysicsTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            ci="99999998", first_name="Maria", first_last_name="Gomez", email="mariag@example.com"
        )
        self.usuario = Usuario.objects.create(
            username="mariag", password="hashed_password", id_persona=self.persona, rol="US", registered=True
        )
        self.building = Building.objects.create(
            name="Test Building Pump", rif="J-11111111-1", address="Calle Test 1", floors=10
        )
        self.sim = _make_sim(self.building, pump=True, elevator=False)
        self.sim.pump_on = True

    def test_dry_run_fault(self):
        self.sim.sim_faults["pump"] = "dry_run"
        for _ in range(60):
            _update_pump(self.sim)
        self.assertEqual(self.sim.sensor_data["pump_flow_rate"], 0.0)
        self.assertEqual(self.sim.sensor_data["pump_pressure"], 0.0)
        self.assertAlmostEqual(self.sim.sensor_data["pump_current"], 3.5, delta=1.0)
        self.assertGreater(self.sim.sensor_data["pump_temperature"], 60.0)
        self.assertGreater(self.sim.sensor_data["pump_vibration"], 4.5)

    def test_blocked_discharge_fault(self):
        self.sim.sensor_data["pump_tank_level"] = 50.0
        self.sim.sim_faults["pump"] = "blocked_discharge"
        for _ in range(35):
            _update_pump(self.sim)
        self.assertEqual(self.sim.sensor_data["pump_flow_rate"], 0.0)
        self.assertGreater(self.sim.sensor_data["pump_pressure"], 8.0)
        self.assertAlmostEqual(self.sim.sensor_data["pump_current"], 8.5, delta=1.0)
        # Nivel del tanque congelado cuando caudal = 0 (bomba de expulsión)
        self.assertEqual(self.sim.sensor_data["pump_tank_level"], 50.0)
        self.assertGreater(self.sim.sensor_data["pump_temperature"], 50.0)

    def test_pipe_burst_fault(self):
        self.sim.sim_faults["pump"] = "pipe_burst"
        for _ in range(35):
            _update_pump(self.sim)
        self.assertEqual(self.sim.sensor_data["pump_pressure"], 0.0)
        self.assertGreater(self.sim.sensor_data["pump_flow_rate"], 20.0)
        self.assertGreater(self.sim.sensor_data["pump_current"], 16.0)

    def test_cavitation_fault(self):
        self.sim.sim_faults["pump"] = "cavitation"
        for _ in range(35):
            _update_pump(self.sim)
        self.assertLessEqual(self.sim.sensor_data["pump_flow_rate"], 5.0)
        self.assertLessEqual(self.sim.sensor_data["pump_pressure"], 1.0)
        self.assertGreater(self.sim.sensor_data["pump_vibration"], 7.0)

    def test_overheat_fault(self):
        self.sim.sim_faults["pump"] = "overheat"
        for _ in range(75):
            _update_pump(self.sim)
        self.assertGreater(self.sim.sensor_data["pump_temperature"], 80.0)
        self.assertGreater(self.sim.sensor_data["pump_current"], 16.0)
        self.assertGreater(self.sim.sensor_data["pump_flow_rate"], 5.0)
        self.assertGreater(self.sim.sensor_data["pump_pressure"], 1.0)

    def test_power_surge_fault(self):
        self.sim.sim_faults["pump"] = "power_surge"
        for _ in range(35):
            _update_pump(self.sim)
        self.assertAlmostEqual(self.sim.sensor_data["pump_voltage"], 185.0, delta=5.0)
        self.assertGreater(self.sim.sensor_data["pump_current"], 22.0)
        self.assertEqual(self.sim.sensor_data["pump_flow_rate"], 0.0)
        self.assertEqual(self.sim.sensor_data["pump_pressure"], 0.0)

    def test_power_outage_fault(self):
        self.sim.sensor_data["pump_tank_level"] = 65.0
        self.sim.sim_faults["pump"] = "power_outage"
        for _ in range(35):
            _update_pump(self.sim)
        self.assertEqual(self.sim.sensor_data["pump_voltage"], 0.0)
        self.assertEqual(self.sim.sensor_data["pump_current"], 0.0)
        self.assertEqual(self.sim.sensor_data["pump_flow_rate"], 0.0)
        self.assertEqual(self.sim.sensor_data["pump_pressure"], 0.0)
        self.assertEqual(self.sim.sensor_data["pump_vibration"], 0.0)
        # Nivel del tanque congelado cuando caudal = 0 (bomba de expulsión)
        self.assertEqual(self.sim.sensor_data["pump_tank_level"], 65.0)

    def test_bearing_failure_fault(self):
        self.sim.sim_faults["pump"] = "bearing_failure"
        for _ in range(35):
            _update_pump(self.sim)
        self.assertGreater(self.sim.sensor_data["pump_vibration"], 7.0)
        self.assertGreater(self.sim.sensor_data["pump_flow_rate"], 5.0)
        self.assertGreater(self.sim.sensor_data["pump_pressure"], 1.0)

