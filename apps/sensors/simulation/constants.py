from apps.sensors.sensor_config import SENSOR_RANGES as _SR
MAX_HISTORY_SIZE: int = 500
LOG_SIM: bool = True
SIMULTANEOUS_FAIL_PROB: float = 0.3
MAX_DOOR_CLOSE_ATTEMPTS: int = 3
RANDOM_FAULT_PROB: float = 0.0

PUMP_P0: float = 7.0
PUMP_K: float = 0.012
T_AMBIENT: float = 22.0

CRUISING_SPEED: float = 1.0
ACCELERATION: float = 0.8
FLOOR_HEIGHT: float = 3.5
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
OVERLOAD_EXTRA_KG: float = 900.0        # Extra virtual mass during overload fault (kg) — garantiza total > 800 kg con cabina vacía (spec: bloqueo en >800 kg)

# Power outage phases (seconds)
POWER_OUTAGE_BRAKE_TIME: float = 0.1    # Emergency brake — frenos mecánicos actúan en ≤1 tick (spec: speed→0 inmediato)
POWER_OUTAGE_BATTERY_WAIT: float = 3.0  # Wait before battery rescue activates
BATTERY_RESCUE_SPEED: float = 0.3       # Low-speed rescue (m/s)

# Safety brake overspeed threshold (× CRUISING_SPEED)
OVERSPEED_GOVERNOR_TRIGGER: float = 1.25
OVERSPEED_ACCEL_RATE: float = 0.5       # Acceleration rate when governor failed (m/s²)

# Door obstruction retry interval (seconds)

# Motor stall detection
STUCK_THRESHOLD_TICKS: int = 3          # Consecutive ticks at speed≈0 before alarm
STUCK_SPEED_EPSILON: float = 0.01       # Speed threshold considered "zero"

# Elevator motor thermal & electrical constants
ELEVATOR_MOTOR_TEMP_AMBIENT: float = 25.0
ELEVATOR_MOTOR_TEMP_ALERT: float = 90.0
ELEVATOR_MOTOR_RATED_CURRENT: float = 28.0

DEFAULT_SENSOR_DATA: dict = {
    # ── SISTEMA BOMBA — Reposo Seguro ──────────────────────────────────────
    "pump_flow_rate":    0.0,      # Apagada
    "pump_pressure":     1.0,      # Presión atmosférica base (bar)
    "pump_temperature":  25.0,     # Temperatura ambiente (°C)
    "pump_vibration":    0.0,      # Detenida (mm/s)
    "pump_tank_level":   50.0,     # Nivel medio seguro (%)
    "pump_voltage":      220.0,    # Tensión de red disponible en reposo seguro (220 V monofásico)
    "pump_current":      0.0,      # Sin consumo (A)
    "pump_water_quality": 150.0,   # Calidad de agua estándar (ppm)
    # ── SISTEMA ELEVADOR — Reposo Seguro ───────────────────────────────────
    "elev_position":     0,        # Planta baja (piso)
    "elev_speed":        0.0,      # Detenido (m/s)
    "elev_load":         0,        # Vacío (kg)
    "elev_door_status":  "closed", # Puerta cerrada
    "elev_temperature":  25.0,     # Temperatura ambiente (°C)
    "elev_current":      0.0,      # Sin consumo (A)
    "elev_vibration":    0.0,      # Detenido (mm/s)
    "elev_voltage":      380.0,    # Tensión trifásica nominal lista (V)
    "elevator_state":    "IDLE",
}

MIN_SIM_SPEED: float = 0.1
MAX_SIM_SPEED: float = 10.0

ELEVATOR_LOAD_ALERT: float = 700.0
ELEVATOR_TEMP_ALERT: float = 90.0

CLEAR_FAULT_MIN_FLOW: float = _SR["pump_flow_rate"][1] * 0.25       # 15.0
CLEAR_FAULT_MIN_PRESSURE: float = _SR["pump_pressure"][1] * 0.25    # 3.0
CLEAR_FAULT_MAX_VIBRATION: float = _SR["pump_vibration"][1] * 0.33  # 5.0
CLEAR_FAULT_VOLTAGE_LOW: float = _SR["pump_voltage"][0] + (_SR["pump_voltage"][1] - _SR["pump_voltage"][0]) * 0.3   # 204.0
CLEAR_FAULT_VOLTAGE_HIGH: float = _SR["pump_voltage"][0] + (_SR["pump_voltage"][1] - _SR["pump_voltage"][0]) * 0.7  # 236.0
CLEAR_FAULT_MAX_LOAD: float = _SR["elev_load"][1] * 0.42             # 500.0

MAX_STEPS_PER_SECOND: dict[str, float] = {
    "pump_flow_rate": 5.0,
    "pump_pressure": 1.0,
    "pump_temperature": 5.0,
    "pump_vibration": 2.0,
    "pump_tank_level": 10.0,
    "pump_voltage": 15.0,
    "pump_current": 5.0,
    "pump_water_quality": 20.0,
    "elev_speed": 1.0,
    "elev_load": 150.0,
    "elev_position": 1.0,
    "elev_temperature": 3.0,
    "elev_current": 8.0,
    "elev_vibration": 2.0,
    "elev_voltage": 15.0,
}
