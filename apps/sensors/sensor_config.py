VAR_NAMES = {
    "pump_flow_rate":      "Caudal",
    "pump_pressure":       "Presión",
    "pump_temperature":    "Temperatura",
    "pump_vibration":      "Vibración",
    "pump_tank_level":     "Nivel de tanque",
    "pump_voltage":        "Voltaje",
    "pump_current":        "Corriente",
    "elev_position":       "Posición",
    "elev_speed":          "Velocidad",
    "elev_load":           "Carga",
    "elev_door_status":    "Estado de puerta",
    "elev_temperature":    "Temperatura",
    "elev_current":        "Corriente",
}

UNITS = {
    "pump_flow_rate":    "l/s",
    "pump_pressure":     "bar",
    "pump_temperature":  "°C",
    "pump_vibration":    "mm/s",
    "pump_tank_level":   "%",
    "pump_voltage":      "V",
    "pump_current":      "A",
    "elev_position":     "piso",
    "elev_speed":        "m/s",
    "elev_load":         "kg",
    "elev_door_status":  "",
    "elev_temperature":  "°C",
    "elev_current":      "A",
}

RISK_NORMAL      = "Normal"
RISK_ALTO        = "Alto"
RISK_CRITICO     = "Crítico"
RISK_RESUELTA    = "Resuelta"

SEVERITY_LEVELS = [RISK_NORMAL, RISK_ALTO, RISK_CRITICO]
HISTORY_SEVERITY_LEVELS = [RISK_RESUELTA, RISK_ALTO, RISK_CRITICO]

RISK_COLORS = {
    RISK_NORMAL: {
        "pdf":     {"bg": (240, 253, 244), "text": (22, 163, 74)},
        "email":   {"bg": "#f0fdf4", "border": "#bbf7d0", "text": "#16a34a"},
        "desc":    "Valores normales de funcionamiento",
    },
    RISK_ALTO: {
        "pdf":     {"bg": (255, 247, 237), "text": (217, 119, 6)},
        "email":   {"bg": "#fff7ed", "border": "#fed7aa", "text": "#d97706"},
        "desc":    "Fuera de rango seguro",
    },
    RISK_CRITICO: {
        "pdf":     {"bg": (254, 242, 242), "text": (185, 28, 28)},
        "email":   {"bg": "#fef2f2", "border": "#fecaca", "text": "#b91c1c"},
        "desc":    "Estado de peligro, acción inmediata",
    },
    RISK_RESUELTA: {
        "pdf":     {"bg": (240, 253, 244), "text": (22, 163, 74)},
        "email":   {"bg": "#f0fdf4", "border": "#bbf7d0", "text": "#16a34a"},
        "desc":    "Alerta resuelta",
    },
}

SEVERITY_DISPLAY_LEVELS = [
    (risk, v["pdf"]["bg"], v["pdf"]["text"], v["desc"])
    for risk, v in RISK_COLORS.items()
    if risk != RISK_RESUELTA
]

HISTORY_SEVERITY_DISPLAY_LEVELS = [
    (risk, v["pdf"]["bg"], v["pdf"]["text"], v["desc"])
    for risk, v in RISK_COLORS.items()
    if risk in HISTORY_SEVERITY_LEVELS
]

RISK_STYLES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    risk: (v["pdf"]["bg"], v["pdf"]["text"])
    for risk, v in RISK_COLORS.items()
}

EMAIL_COLOR_PALETTE: dict[str, dict[str, str]] = {
    risk: v["email"]
    for risk, v in RISK_COLORS.items()
}
EMAIL_FALLBACK_COLORS: dict[str, str] = {
    "bg": "#f1f5f9", "border": "#cbd5e1", "text": "#475569",
}

USER_STATS_COLORS = {
    "total":      {"fill": (235, 241, 249), "text": (30, 58, 95)},
    "registrados": {"fill": (240, 253, 244), "text": (22, 163, 74)},
    "pendientes": {"fill": (255, 247, 237), "text": (217, 119, 6)},
    "edificios":  {"fill": (249, 250, 251), "text": (55, 65, 81)},
}

NO_RISK_VARS = []

LIMITS_EXCLUDE_VARS = [
    "pump_tank_level", "pump_flow_rate",
    "elev_position", "elev_door_status",
]

ZERO_IS_CRITICAL_VARS = {"pump_flow_rate", "pump_pressure"}

BOOLEAN_VARS = set()

ENUM_VARS = {"elev_door_status"}

ENUM_RISK_VALUES = {
    "elev_door_status": {"open", "closing"},
}

PUMP_VARS = [
    "pump_flow_rate",
    "pump_pressure",
    "pump_temperature",
    "pump_vibration",
    "pump_tank_level",
    "pump_voltage",
    "pump_current",
]

ELEVATOR_VARS = [
    "elev_position",
    "elev_speed",
    "elev_load",
    "elev_door_status",
    "elev_temperature",
    "elev_current",
]

_ELEVATOR_NUMERIC = [v for v in ELEVATOR_VARS if v not in NO_RISK_VARS and v not in BOOLEAN_VARS and v not in ENUM_VARS]

STATS_VARS = PUMP_VARS + _ELEVATOR_NUMERIC

VALUE_DISPLAY_ES = {
    "elev_door_status": {
        "open":     "Abierta",
        "closed":   "Cerrada",
        "opening":  "Abriendo",
        "closing":  "Cerrando",
        "true":     "Bloqueada",
        "false":    "Normal",
    },
}

DEFAULT_THRESHOLDS = {
    "pump_flow_rate":   {"direction": "lower",  "low": 8.0,  "medium": 5.0, "high": 2.0},
    "pump_pressure":    {"direction": "range",  "low": 2.0,  "high": 8.0},
    "pump_temperature": {"direction": "higher", "low": 70,   "medium": 85,  "high": 100},
    "pump_vibration":   {"direction": "higher", "low": 4,    "medium": 7,   "high": 10},
    "pump_tank_level":  {"direction": "lower",  "low": 30,   "medium": 15,  "high": 5},
    "pump_voltage":     {"direction": "range",  "low": 200,  "high": 240},
    "pump_current":     {"direction": "higher", "low": 30,   "medium": 40,  "high": 50},
    "elev_speed":       {"direction": "higher", "low": 2.5,  "medium": 3.0, "high": 4.0},
    "elev_load":        {"direction": "higher", "low": 600,  "medium": 800, "high": 900},
    "elev_temperature": {"direction": "higher", "low": 70,   "medium": 85,  "high": 90},
    "elev_current":     {"direction": "higher", "low": 32,   "medium": 40,  "high": 45},
}

FALLBACK_ACTION_TEMPLATE: str = "Verifica el sensor {}. Programa inspección preventiva."

ACTIONS: dict[str, dict[str, str]] = {
    "pump_flow_rate": {
        RISK_NORMAL: "Caudal dentro del rango normal. Monitoreo rutinario activo.",
        RISK_ALTO: "Caudal significativamente bajo. Verifica posibles fugas o fallas parciales en la bomba.",
        RISK_CRITICO: "Caudal crítico bajo (flujo casi nulo). Parada preventiva de bomba activada. Inspecciona la tubería de succión y la bomba.",
    },
    "pump_pressure": {
        RISK_NORMAL: "Presión dentro del rango normal. Monitoreo rutinario activo.",
        RISK_ALTO: "Presión fuera del rango operativo seguro (2.0 - 8.0 bar). Verifica posibles fugas (presión baja) o bloqueos (presión alta).",
        RISK_CRITICO: "Presión en nivel crítico (flujo nulo o sobrepresión extrema). Detén la bomba de inmediato y verifique la tubería.",
    },
    "pump_temperature": {
        RISK_NORMAL: "Temperatura normal. Ventilación adecuada.",
        RISK_ALTO: "Temperatura alta del motor de bomba. Aumenta la ventilación de la sala de máquinas.",
        RISK_CRITICO: "Temperatura crítica del motor. Riesgo de sobrecalentamiento y fusión. Apagado de emergencia y verificación del sistema de enfriamiento.",
    },
    "pump_vibration": {
        RISK_NORMAL: "Vibración normal. Alineación mecánica correcta.",
        RISK_ALTO: "Vibración por encima del estándar. Programa mantenimiento mecánico.",
        RISK_CRITICO: "Vibración mecánica severa. Desalineación grave o falla de rodamiento. Detén el equipo inmediatamente.",
    },
    "pump_tank_level": {
        RISK_NORMAL: "Nivel de tanque bajo. Monitorea el reabastecimiento.",
        RISK_ALTO: "Nivel de tanque alto. Monitorea el llenado automático.",
        RISK_CRITICO: "Nivel de tanque crítico. Riesgo de cavitación de bomba. Detén succión y rellena el tanque urgentemente.",
    },
    "pump_voltage": {
        RISK_NORMAL: "Voltaje dentro del rango nominal (200-240 V).",
        RISK_ALTO: "Inestabilidad de voltaje (fuera del rango 200 V - 240 V). Riesgo para componentes electrónicos.",
        RISK_CRITICO: "Fluctuación crítica de voltaje. Desconecta el equipo para evitar daños.",
    },
    "pump_current": {
        RISK_NORMAL: "Corriente del motor dentro del rango operativo.",
        RISK_ALTO: "Corriente del motor por encima del límite recomendado. Verifica carga y estado del bobinado.",
        RISK_CRITICO: "Amperaje crítico (sobrecarga eléctrica). Apagado automático por protección activo.",
    },
    "elev_speed": {
        RISK_NORMAL: "Velocidad de elevador normal.",
        RISK_ALTO: "Velocidad de elevador por encima del límite seguro. Programa inspección del VFD.",
        RISK_CRITICO: "Sobrepaso de velocidad crítico. Frenado de emergencia activado. Inspección de seguridad obligatoria.",
    },
    "elev_load": {
        RISK_NORMAL: "Carga de cabina normal.",
        RISK_ALTO: "Carga de cabina cerca del límite de diseño. Monitorea el comportamiento del motor.",
        RISK_CRITICO: "Sobrecarga de cabina de elevador. Retira el exceso de peso para reanudar operación.",
    },
    "elev_door_status": {
        RISK_NORMAL: "Estado de puerta normal.",
        RISK_ALTO: "Fallo de cierre de puerta. Verifica mecanismo de enclavamiento.",
        RISK_CRITICO: "Puerta sin respuesta. Detén operación e inspeccione el sistema de puerta.",
    },
    "elev_temperature": {
        RISK_NORMAL: "Temperatura del motor de tracción normal.",
        RISK_ALTO: "Temperatura del motor de tracción alta. Monitorea el sistema de ventilación de la sala de máquinas.",
        RISK_CRITICO: "Temperatura crítica del motor de tracción. Riesgo de daño a bobinas. Parada de emergencia y verificación del enfriamiento.",
    },
    "elev_current": {
        RISK_NORMAL: "Corriente del motor de tracción normal.",
        RISK_ALTO: "Corriente del motor de tracción elevada. Verifica carga de cabina y estado del variador.",
        RISK_CRITICO: "Corriente crítica del motor de tracción. Posible rotor bloqueado o sobrecarga severa. Apagado de emergencia.",
    },
}

SIM_TICK_INTERVAL = 1

COOLDOWN_SECONDS: int = 1800
MAX_PDF_EVENTS: int = 200
PAGE_SIZE: int = 15
SMTP_TIMEOUT: int = 15
API_HISTORY_LIMIT: int = 50
PAYLOAD_HISTORY_SLICE: int = 200

SENSOR_RANGES = {
    "pump_flow_rate":   (0, 60),
    "pump_pressure":    (0, 12),
    "pump_temperature": (22.0, 130),
    "pump_vibration":   (0, 15),
    "pump_tank_level":  (0, 100),
    "pump_voltage":     (180, 260),
    "pump_current":     (0, 70),
    "elev_speed":       (0, 6),
    "elev_load":        (0, 1200),
    "elev_position":    (0, 100),
    "elev_temperature": (25.0, 120),
    "elev_current":     (0, 80),
}

FAULT_NAMES_ES = {
    "dry_run":             "Sequía",
    "blocked_discharge":   "Descarga bloqueada",
    "pipe_burst":          "Ruptura de tubería",
    "cavitation":          "Cavitación",
    "overheat":            "Sobrecalentamiento",
    "power_surge":         "Sobrecarga eléctrica",
    "power_outage":        "Corte eléctrico",
    "motor_stuck":         "Motor atascado",
    "door_blocked":        "Puerta bloqueada",
    "overspeed":           "Exceso de velocidad",
    "overload":            "Sobrecarga",
    "pos_sensor_fail":     "Fallo del sensor de posición",
    "commercial_power_outage": "Corte de energía comercial",
}

PUMP_FAULT_KEYS = ("dry_run", "blocked_discharge", "pipe_burst", "cavitation", "overheat", "power_surge", "power_outage")
ELEVATOR_FAULT_KEYS = ("motor_stuck", "door_blocked", "overspeed", "overload", "pos_sensor_fail", "commercial_power_outage")

FAULT_AFFECTED_VARIABLES: dict[str, list[str]] = {
    "dry_run":               ["pump_flow_rate", "pump_pressure", "pump_temperature", "pump_vibration", "pump_tank_level", "pump_current"],
    "blocked_discharge":     ["pump_flow_rate", "pump_pressure", "pump_vibration", "pump_temperature", "pump_current"],
    "pipe_burst":            ["pump_flow_rate", "pump_pressure", "pump_vibration", "pump_temperature", "pump_current", "pump_tank_level"],
    "cavitation":            ["pump_flow_rate", "pump_vibration", "pump_pressure", "pump_temperature"],
    "overheat":              ["pump_temperature", "pump_vibration"],
    "power_surge":           ["pump_flow_rate", "pump_pressure", "pump_voltage", "pump_current", "pump_temperature", "pump_vibration"],
    "power_outage":          ["pump_voltage", "pump_current", "pump_flow_rate", "pump_pressure", "pump_vibration", "pump_temperature"],
    "motor_stuck":           ["elev_temperature", "elev_speed", "elev_current", "elev_door_status"],
    "door_blocked":          ["elev_door_status", "elev_speed"],
    "overspeed":             ["elev_speed", "elev_current", "elev_door_status"],
    "overload":              ["elev_load", "elev_door_status", "elev_speed", "elev_current"],
    "pos_sensor_fail":       ["elev_position", "elev_speed", "elev_door_status"],
    "commercial_power_outage": ["elev_current", "elev_speed", "elev_door_status", "elev_temperature"],
}

UNKNOWN_PERSON_NAME: str = "Sin nombre"
UNKNOWN_EMAIL_LABEL: str = "Sin correo"
