from apps.sensors.sensor_config import RATIONING_THRESHOLD, SENSOR_RANGES as _SR
MAX_HISTORY_SIZE: int = 500
MAX_LOG_ENTRIES: int = 100
SIMULATION_NORMAL_DURATION: int = 10
LOG_SIM: bool = True
SIMULTANEOUS_FAIL_PROB: float = 0.3
DOOR_CLOSE_SUCCESS_PROB: float = 0.25
DOOR_OPEN_PROB: float = 0.4
MAX_DOOR_CLOSE_ATTEMPTS: int = 3
FAULT_AUTO_CLEAR_SECONDS: int = 120
RANDOM_FAULT_PROB: float = 0.0

PUMP_P0: float = 7.0
PUMP_K: float = 0.012
TANK_AREA: float = 2.5
T_AMBIENT: float = 22.0
TANK_CAPACITY: float = 100.0

FLOOR_COUNT: int = 20
CRUISING_SPEED: float = 2.0
ACCELERATION: float = 0.8
FLOOR_HEIGHT: float = 3.5
DOOR_CYCLE_TICKS: int = 3
PASSENGER_WAIT_TICKS: int = 8

# Physical constants
G: float = 9.81                         # Gravity (m/s²)
JERK: float = 0.5                       # Jerk limit for S-curve comfort (m/s³)
CABIN_EMPTY_MASS: float = 800.0         # Empty cabin mass (kg)
RATED_LOAD: float = 500.0               # Rated load capacity (kg)
COUNTERWEIGHT_MASS: float = 1025.0      # M_cw = M_empty + 0.45 * M_rated = 800 + 0.45*500
MOTOR_EFFICIENCY: float = 0.85          # Motor + drive system efficiency

# Door timing (seconds, real-world range: 1.5–2.5 s)
DOOR_OPEN_TIME: float = 2.0
DOOR_CLOSE_TIME: float = 2.0

# Overload fault
OVERLOAD_EXTRA_KG: float = 500.0        # Extra virtual mass during overload fault (kg)

# Power outage phases (seconds)
POWER_OUTAGE_BRAKE_TIME: float = 1.0    # Emergency brake deceleration phase
POWER_OUTAGE_BATTERY_WAIT: float = 3.0  # Wait before battery rescue activates
BATTERY_RESCUE_SPEED: float = 0.3       # Low-speed rescue (m/s)

# Safety brake overspeed threshold (× CRUISING_SPEED)
OVERSPEED_GOVERNOR_TRIGGER: float = 1.25
OVERSPEED_ACCEL_RATE: float = 0.5       # Acceleration rate when governor failed (m/s²)

# Door obstruction retry interval (seconds)
DOOR_OBSTRUCTION_RETRY_INTERVAL: float = 3.0

# Motor stall detection
STUCK_THRESHOLD_TICKS: int = 3          # Consecutive ticks at speed≈0 before alarm
STUCK_SPEED_EPSILON: float = 0.01       # Speed threshold considered "zero"

DEFAULT_SENSOR_DATA: dict = {
    "flow_rate": 0.0,
    "pressure": 0.0,
    "temperature": 25.0,
    "vibration": 0.0,
    "tank_level": 80.0,
    "position": 0,
    "speed": 0.0,
    "load": 0,
    "trip_count": 0,
    "door_status": "closed",
    "energy": 0.0,
    "pump_energy": 0.0,
    "voltage": 220.0,
    "current": 0.0,
    "motor_stuck": False,
    "elevator_state": "IDLE",
    "door_close_attempts": 0,
}

MIN_SIM_SPEED: float = 0.1
MAX_SIM_SPEED: float = 10.0

REFILL_TIMER_TICKS: int = 15

ELEVATOR_LOAD_ALERT: float = 700.0
ELEVATOR_TEMP_ALERT: float = 90.0

CLEAR_FAULT_MIN_FLOW: float = _SR["flow_rate"][1] * 0.25       # 15.0
CLEAR_FAULT_MIN_PRESSURE: float = _SR["pressure"][1] * 0.25    # 3.0
CLEAR_FAULT_MAX_VIBRATION: float = _SR["vibration"][1] * 0.33  # 5.0
CLEAR_FAULT_VOLTAGE_LOW: float = _SR["voltage"][0] + (_SR["voltage"][1] - _SR["voltage"][0]) * 0.3   # 204.0
CLEAR_FAULT_VOLTAGE_HIGH: float = _SR["voltage"][0] + (_SR["voltage"][1] - _SR["voltage"][0]) * 0.7  # 236.0
CLEAR_FAULT_MAX_LOAD: float = _SR["load"][1] * 0.42             # 500.0

MAX_STEPS_PER_SECOND: dict[str, float] = {
    "flow_rate": 5.0,
    "pressure": 1.0,
    "temperature": 5.0,
    "vibration": 2.0,
    "tank_level": 10.0,
    "voltage": 15.0,
    "current": 5.0,
    "speed": 1.0,
    "load": 150.0,
    "energy": 2.0,
    "pump_energy": 2.0,
    "position": 1.0,
    "trip_count": 1000.0,
}


