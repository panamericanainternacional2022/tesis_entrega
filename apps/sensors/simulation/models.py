import random
from collections import deque

from apps.sensors.simulation.constants import FLOOR_COUNT, DEFAULT_SENSOR_DATA


class BuildingSimulator:
    def __init__(self, edificio_id: int, nombre: str, equipment_types: set = None, floors: int = 20):
        self.edificio_id: int = edificio_id
        self.nombre: str = nombre
        self.equipment_types: set = equipment_types or set()
        self.floors: int = floors
        self.sensor_data: dict = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
        self.has_pump: bool = "bomba" in self.equipment_types
        self.has_elevator: bool = "elevador" in self.equipment_types
        self.pump_on: bool = False
        self.elevator_on: bool = False
        self.active_alerts: dict = {}
        self.door_close_attempts: int = 0
        self.history: list = []
        self.pending_notifications: deque = deque()
        self.last_email_sent_time: float = 0.0
        self.last_email_sent_time_per_var: dict = {}
        self.manual_overrides: dict = {}
        self.manual_targets: dict = {}

        self.manual_pump_override: bool = False
        self.manual_elevator_override: bool = False

        self.sim_paused: bool = True
        self.sim_started: bool = False
        self.sim_speed: float = 1.0
        self.sim_faults: dict = {}
        self.fault_injected_at: dict = {}

        self._pump_demand: float = 15.0
        self._pump_refill_timer: float = 0
        self._pump_failure_timer: float = 0
        self._pump_failure_active: bool = False
        self._pump_failure_var = None
        self._pump_start_grace_ticks: int = 0

        self._elev_state: str = "IDLE"
        self._elev_timer: float = 0
        self._elev_current_accel: float = 0.0    # Actual acceleration (for S-curve)
        self._elev_stuck_timer: float = 0.0      # Consecutive stall ticks
        self._elev_prev_spd: float = 0.0         # Speed at start of tick
        if self.has_elevator:
            self.sensor_data["position"] = 0
            self._elev_position_meters = 0.0
            self._elev_target_floor = 0
        else:
            self._elev_target_floor = 0
            self._elev_position_meters = 0.0
        self._elev_direction: int = 1
        self._elev_at_floor: bool = True
        self._elev_prev_position: float = 0

        # Fault physical parameters (mutated by fault handlers, consumed by FSM)
        self._elev_motor_torque_factor: float = 1.0     # 0.0 = motor stuck
        self._elev_door_obstructed: bool = False         # Door physically blocked
        self._elev_speed_governor_failed: bool = False   # Overspeed governor failed
        self._elev_overload_extra_kg: float = 0.0        # Extra virtual load for overload fault
        self._elev_pos_sensor_stuck: bool = False        # Position sensor frozen
        self._elev_power_available: bool = True          # False = power outage
        self._elev_brake_failed: bool = False            # Mechanical brake failed
        self._elev_power_outage_timer: float = 0.0       # Timer for power outage phases
        self._elev_power_outage_complete: bool = False   # True once battery rescue finishes

    def __repr__(self) -> str:
        return (
            f"<BuildingSimulator edificio_id={self.edificio_id} "
            f"nombre={self.nombre!r} eq_types={self.equipment_types}>"
        )
