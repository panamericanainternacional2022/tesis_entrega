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
    "elev_vibration":      "Vibración",
    "elev_voltage":        "Voltaje",
    "pump_water_quality":  "Calidad de agua",
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
    "elev_vibration":    "mm/s",
    "elev_voltage":      "V",
    "pump_water_quality":"ppm",
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



BOOLEAN_VARS = set()

ENUM_VARS = {"elev_door_status"}

ENUM_RISK_VALUES = {
    "elev_door_status": {"open"},
}

PUMP_VARS = [
    "pump_flow_rate",
    "pump_pressure",
    "pump_temperature",
    "pump_vibration",
    "pump_tank_level",
    "pump_voltage",
    "pump_current",
    "pump_water_quality",
]

ELEVATOR_VARS = [
    "elev_position",
    "elev_speed",
    "elev_load",
    "elev_door_status",
    "elev_temperature",
    "elev_current",
    "elev_vibration",
    "elev_voltage",
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
    # ── SISTEMA BOMBA ───────────────────────────────────────────────────────
    # Normal: 0-15 | Alto: >15 | Crítico: >20
    "pump_flow_rate":    {"direction": "higher", "high": 15.0,  "critic": 20.0},
    # Normal: 1.0-6.0 | Alto: fuera del rango | Crítico: fuera del rango crítico
    "pump_pressure":     {"direction": "range",  "high": 1.0,   "critic": 6.0,
                          "crit_low": 0.5, "crit_high": 8.0},
    # Normal: 20-60 | Alto: >60 | Crítico: >85
    "pump_temperature":  {"direction": "higher", "high": 60.0,  "critic": 85.0},
    # Normal: 0-4.5 | Alto: >4.5 | Crítico: >7.1
    "pump_vibration":    {"direction": "higher", "high": 4.5,   "critic": 7.1},
    # Normal: 20-85 | Alto: fuera del rango | Crítico: fuera del rango crítico
    "pump_tank_level":   {"direction": "range",  "high": 20.0,  "critic": 85.0,
                          "crit_low": 10.0, "crit_high": 95.0},
    # Normal: 210-230 | Alto: fuera del rango | Crítico: fuera del rango crítico
    "pump_voltage":      {"direction": "range",  "high": 210.0, "critic": 230.0,
                          "crit_low": 198.0, "crit_high": 242.0},
    # Normal: 0-16 | Alto: >16 | Crítico: >22
    "pump_current":      {"direction": "higher", "high": 16.0,  "critic": 22.0},
    # Normal: 0-300 | Alto: >300 | Crítico: >500
    "pump_water_quality":{"direction": "higher", "high": 300.0, "critic": 500.0},
    # ── SISTEMA ELEVADOR ────────────────────────────────────────────────────
    # Normal: 0-1.2 | Alto: >1.2 | Crítico: >1.6
    "elev_speed":        {"direction": "higher", "high": 1.2,   "critic": 1.6},
    # Normal: 0-600 | Alto: >600 | Crítico: >800
    "elev_load":         {"direction": "higher", "high": 600.0, "critic": 800.0},
    # Normal: 20-50 | Alto: >50 | Crítico: >75
    "elev_temperature":  {"direction": "higher", "high": 50.0,  "critic": 75.0},
    # Normal: 0-20 | Alto: >20 | Crítico: >30
    "elev_current":      {"direction": "higher", "high": 20.0,  "critic": 30.0},
    # Normal: 0-2.0 | Alto: >2.0 | Crítico: >5.0
    "elev_vibration":    {"direction": "higher", "high": 2.0,   "critic": 5.0},
    # Normal: 360-400 V | Alto: fuera del rango | Crítico: fuera del rango crítico
    "elev_voltage":      {"direction": "range",  "high": 360.0, "critic": 400.0,
                          "crit_low": 342.0, "crit_high": 418.0},
}

FALLBACK_ACTION_TEMPLATE: str = "Verifica el sensor {}. Programa inspección preventiva."

ACTIONS: dict[str, dict[str, str]] = {
    "pump_flow_rate": {
        RISK_NORMAL:  "Caudal dentro del rango normal. Monitoreo rutinario activo.",
        RISK_ALTO:    "El caudal de la bomba se encuentra por encima del rango operativo normal.",
        RISK_CRITICO: "El caudal de la bomba ha superado el umbral crítico. Riesgo de sobrepresión hidráulica y daño en la tubería.",
    },
    "pump_pressure": {
        RISK_NORMAL:  "Presión dentro del rango normal. Monitoreo rutinario activo.",
        RISK_ALTO:    "La presión de la bomba está fuera del rango operativo seguro.",
        RISK_CRITICO: "La presión de la bomba se encuentra en nivel crítico. Riesgo de ruptura de tubería o colapso de flujo.",
    },
    "pump_temperature": {
        RISK_NORMAL:  "Temperatura normal. Ventilación adecuada.",
        RISK_ALTO:    "La temperatura del motor de la bomba supera el umbral seguro.",
        RISK_CRITICO: "La temperatura del motor de la bomba ha alcanzado el nivel crítico. Riesgo de fallo térmico del devanado.",
    },
    "pump_vibration": {
        RISK_NORMAL:  "Vibración normal. Alineación mecánica correcta.",
        RISK_ALTO:    "La vibración de la bomba supera el estándar operativo normal.",
        RISK_CRITICO: "Vibración mecánica severa en la bomba detectada. Riesgo de fallo de rodamiento o desalineación estructural.",
    },
    "pump_tank_level": {
        RISK_NORMAL:  "Nivel de tanque dentro del rango normal.",
        RISK_ALTO:    "El nivel del tanque está fuera del rango seguro de operación.",
        RISK_CRITICO: "El nivel del tanque se encuentra en zona crítica. Riesgo de operación en seco o desbordamiento.",
    },
    "pump_voltage": {
        RISK_NORMAL:  "Voltaje dentro del rango nominal.",
        RISK_ALTO:    "El voltaje de alimentación de la bomba está fuera del rango nominal.",
        RISK_CRITICO: "El voltaje de alimentación de la bomba se encuentra en nivel crítico. Riesgo de daño en componentes electrónicos y bobinados.",
    },
    "pump_current": {
        RISK_NORMAL:  "Corriente del motor dentro del rango operativo.",
        RISK_ALTO:    "La corriente del motor de la bomba supera el límite recomendado.",
        RISK_CRITICO: "La corriente del motor de la bomba ha alcanzado el nivel de sobrecarga eléctrica. Riesgo de disparo de protecciones y fallo del motor.",
    },
    "pump_water_quality": {
        RISK_NORMAL:  "Calidad del agua normal.",
        RISK_ALTO:    "La concentración de sólidos disueltos en el agua supera el umbral normal.",
        RISK_CRITICO: "La calidad del agua ha alcanzado el nivel crítico. Riesgo de daño abrasivo en el impulsor de la bomba.",
    },
    "elev_speed": {
        RISK_NORMAL:  "Velocidad de elevador normal.",
        RISK_ALTO:    "La velocidad de la cabina del elevador supera el límite seguro de operación.",
        RISK_CRITICO: "La velocidad de la cabina del elevador ha superado el umbral crítico. Activación del gobernador de velocidad requerida.",
    },
    "elev_load": {
        RISK_NORMAL:  "Carga de cabina normal.",
        RISK_ALTO:    "La carga de la cabina del elevador se acerca al límite de diseño.",
        RISK_CRITICO: "La carga de la cabina del elevador supera el umbral de bloqueo físico. Sistema de bloqueo de motor activado.",
    },
    "elev_door_status": {
        RISK_NORMAL:  "Estado de puerta normal.",
        RISK_ALTO:    "La puerta del elevador se encuentra en estado de cierre anómalo.",
        RISK_CRITICO: "La puerta del elevador está abierta con la cabina en movimiento o fuera de zona de piso. Condición de seguridad crítica.",
    },
    "elev_temperature": {
        RISK_NORMAL:  "Temperatura del motor de tracción normal.",
        RISK_ALTO:    "La temperatura del motor de tracción del elevador supera el umbral seguro.",
        RISK_CRITICO: "La temperatura del motor de tracción del elevador se encuentra en nivel crítico. Riesgo de fallo térmico de las bobinas.",
    },
    "elev_current": {
        RISK_NORMAL:  "Corriente del motor de tracción normal.",
        RISK_ALTO:    "La corriente del motor de tracción del elevador supera el límite nominal.",
        RISK_CRITICO: "La corriente del motor de tracción del elevador ha alcanzado el nivel crítico. Posible condición de rotor bloqueado o sobrecarga severa.",
    },
    "elev_vibration": {
        RISK_NORMAL:  "Vibración de cabina dentro del rango normal.",
        RISK_ALTO:    "La vibración de la cabina del elevador supera el umbral de confort y seguridad normal.",
        RISK_CRITICO: "Vibración severa detectada en la cabina del elevador. Riesgo de daño estructural en guías de rodamiento y sistema de tracción.",
    },
    "elev_voltage": {
        RISK_NORMAL:  "Voltaje trifásico dentro del rango operativo normal.",
        RISK_ALTO:    "El voltaje de alimentación del elevador está fuera del rango operativo nominal.",
        RISK_CRITICO: "El voltaje de alimentación del elevador se encuentra en nivel crítico. Riesgo de pérdida de fase o disparo de protecciones del variador.",
    },
}

# Textos de alerta especial unificada por falla inyectada.
# Los nombres corresponden exactamente a los selectores del dashboard (FAULT_NAMES_ES).
# Sin prefijo de nivel de riesgo, sin nombre de equipo, sin instrucciones.
FAULT_ALERT_MESSAGES: dict[str, str] = {
    # ── BOMBA ────────────────────────────────────────────────────────────────
    "dry_run":
        "Sequía — El sistema de bombeo opera sin agua en la línea de succión. "
        "Los sensores de caudal, presión, nivel de tanque y corriente presentan "
        "lecturas anómalas simultáneas características de esta condición.",

    "blocked_discharge":
        "Descarga Bloqueada — La línea de descarga de la bomba se encuentra obstruida. "
        "Los sensores de caudal, presión, temperatura y corriente presentan "
        "desviaciones simultáneas características de esta condición.",

    "pipe_burst":
        "Ruptura de Tubería — Se ha detectado una ruptura en la línea de distribución. "
        "Los sensores de caudal, presión, nivel de tanque y temperatura presentan "
        "lecturas anómalas simultáneas características de esta condición.",

    "cavitation":
        "Cavitación — El sistema de bombeo presenta un fenómeno de cavitación. "
        "Los sensores de vibración, presión y caudal presentan oscilaciones "
        "violentas e inestables simultáneas características de esta condición.",

    "overheat":
        "Sobrecalentamiento — El motor de la bomba presenta un ascenso térmico continuo. "
        "Los sensores de temperatura y vibración presentan lecturas por encima "
        "de los límites operativos.",

    "power_surge":
        "Sobrecarga Eléctrica — Se ha detectado una sobrecarga en el sistema eléctrico "
        "de la bomba. Los sensores de corriente, voltaje, temperatura y caudal "
        "presentan desviaciones simultáneas características de esta condición.",

    "power_outage":
        "Corte Eléctrico — La alimentación eléctrica de la bomba ha sido interrumpida. "
        "Los sensores de voltaje, corriente, caudal y presión reportan valores "
        "en cero de forma simultánea.",

    "bearing_failure":
        "Falla de Rodamientos — Se ha detectado degradación en los rodamientos de la bomba. "
        "Los sensores de vibración, temperatura y corriente presentan un incremento "
        "progresivo y simultáneo característico de esta condición.",

    # ── ELEVADOR ─────────────────────────────────────────────────────────────
    "motor_stuck":
        "Motor Atascado — El motor de tracción del elevador se encuentra en condición "
        "de rotor bloqueado. Los sensores de corriente, temperatura, velocidad y vibración "
        "presentan lecturas anómalas simultáneas características de esta condición.",

    "door_blocked":
        "Puerta Bloqueada — La puerta del elevador se encuentra físicamente bloqueada "
        "en posición abierta. El sistema ha abortado el arranque. Los sensores de "
        "estado de puerta y velocidad reflejan esta condición.",

    "overspeed":
        "Exceso de Velocidad — La cabina del elevador ha superado la velocidad crítica "
        "de operación. Los sensores de velocidad, vibración y corriente presentan "
        "lecturas anómalas simultáneas características de esta condición.",

    "overload":
        "Sobrecarga — La carga en la cabina del elevador supera el límite de bloqueo físico. "
        "El motor ha sido bloqueado por el sistema de protección. Los sensores de carga, "
        "velocidad y corriente reflejan esta condición.",

    "pos_sensor_fail":
        "Fallo del Sensor de Posición — El sensor de posición de la cabina del elevador "
        "reporta valores erróneos o congelados. Esta condición activa la parada de "
        "emergencia inmediata del sistema.",

    "commercial_power_outage":
        "Corte de Energía Comercial — La alimentación trifásica del elevador ha sido "
        "interrumpida. El sistema ha activado los frenos mecánicos de seguridad. "
        "Los sensores de voltaje, corriente y velocidad confirman la pérdida de suministro.",

    "traction_loss":
        "Pérdida de Tracción — Se ha detectado un desfase entre la velocidad del motor "
        "y el desplazamiento real de la cabina. Los sensores de posición, vibración, "
        "corriente y velocidad presentan lecturas inconsistentes simultáneas "
        "características de esta condición.",
}

SIM_TICK_INTERVAL = 1

COOLDOWN_SECONDS: int = 1800
MAX_PDF_EVENTS: int = 200
PAGE_SIZE: int = 15
SMTP_TIMEOUT: int = 15
API_HISTORY_LIMIT: int = 50
PAYLOAD_HISTORY_SLICE: int = 200

SENSOR_RANGES = {
    # ── SISTEMA BOMBA — Límites físicos destructivos (simulator.md §2) ──────
    "pump_flow_rate":    (0.0,   60.0),   # sin límite explícito en spec → headroom de fallas
    "pump_pressure":     (0.0,   10.0),   # Límite Máx spec = 10.0 bar (antes 12)
    "pump_temperature":  (-10.0, 100.0),  # Límite Mín=-10°C, Máx=100°C (antes 22.0, 130)
    "pump_vibration":    (0.0,   15.0),   # sin cambio
    "pump_tank_level":   (0.0,  100.0),   # sin cambio
    "pump_voltage":      (0.0,  300.0),   # Límite Mín=0 (corte), Máx=300 V spec (antes 180-260)
    "pump_current":      (0.0,   30.0),   # Límite Máx spec = 30.0 A (antes 70)
    "pump_water_quality":(0.0, 1000.0),   # sin cambio
    # ── SISTEMA ELEVADOR — Límites físicos destructivos (simulator.md §2) ───
    "elev_speed":        (0.0,    3.0),   # Límite Máx spec = 3.0 m/s (antes 6)
    "elev_load":         (0.0, 1200.0),   # sin cambio
    "elev_position":     (0.0,    5.0),   # Rango discreto 0-5 pisos (antes 100)
    "elev_temperature":  (-10.0,  90.0),  # Límite Mín=-10°C, Máx=90°C (antes 25.0, 120)
    "elev_current":      (0.0,   40.0),   # Límite Máx spec = 40.0 A (antes 80)
    "elev_vibration":    (0.0,   10.0),   # Límite Máx spec = 10.0 mm/s (antes 20)
    "elev_voltage":      (0.0,  500.0),   # Límite Máx spec = 500.0 V (antes 450)
}

FAULT_NAMES_ES = {
    "dry_run":             "Sequía",
    "blocked_discharge":   "Descarga bloqueada",
    "pipe_burst":          "Ruptura de tubería",
    "cavitation":          "Cavitación",
    "overheat":            "Sobrecalentamiento",
    "power_surge":         "Sobrecarga eléctrica",
    "power_outage":        "Corte eléctrico",
    "bearing_failure":     "Falla de rodamientos",
    "motor_stuck":         "Motor atascado",
    "door_blocked":        "Puerta bloqueada",
    "overspeed":           "Exceso de velocidad",
    "overload":            "Sobrecarga",
    "pos_sensor_fail":     "Fallo del sensor de posición",
    "commercial_power_outage": "Corte de energía comercial",
    "traction_loss":       "Pérdida de tracción",
}

PUMP_FAULT_KEYS = ("dry_run", "blocked_discharge", "pipe_burst", "cavitation", "overheat", "power_surge", "power_outage", "bearing_failure")
ELEVATOR_FAULT_KEYS = ("motor_stuck", "door_blocked", "overspeed", "overload", "pos_sensor_fail", "commercial_power_outage", "traction_loss")

FAULT_AFFECTED_VARIABLES: dict[str, list[str]] = {
    "dry_run":               ["pump_flow_rate", "pump_pressure", "pump_temperature", "pump_vibration", "pump_tank_level", "pump_current"],
    "blocked_discharge":     ["pump_flow_rate", "pump_pressure", "pump_vibration", "pump_temperature", "pump_current"],
    "pipe_burst":            ["pump_flow_rate", "pump_pressure", "pump_vibration", "pump_temperature", "pump_current", "pump_tank_level"],
    "cavitation":            ["pump_flow_rate", "pump_vibration", "pump_pressure", "pump_temperature"],
    "overheat":              ["pump_temperature", "pump_vibration"],
    "power_surge":           ["pump_flow_rate", "pump_pressure", "pump_voltage", "pump_current", "pump_temperature", "pump_vibration"],
    "power_outage":          ["pump_voltage", "pump_current", "pump_flow_rate", "pump_pressure", "pump_vibration", "pump_temperature"],
    "bearing_failure":       ["pump_vibration", "pump_temperature", "pump_current", "pump_water_quality"],
    "motor_stuck":           ["elev_temperature", "elev_speed", "elev_current", "elev_door_status", "elev_voltage", "elev_vibration"],
    "door_blocked":          ["elev_door_status", "elev_speed"],
    "overspeed":             ["elev_speed", "elev_current", "elev_door_status", "elev_vibration"],
    "overload":              ["elev_load", "elev_door_status", "elev_speed", "elev_current", "elev_vibration"],
    "pos_sensor_fail":       ["elev_position", "elev_speed", "elev_door_status"],
    "commercial_power_outage": ["elev_voltage", "elev_current", "elev_speed", "elev_door_status", "elev_temperature"],
    "traction_loss":         ["elev_position", "elev_speed", "elev_current", "elev_vibration", "elev_temperature"],
}

UNKNOWN_PERSON_NAME: str = "Sin nombre"
UNKNOWN_EMAIL_LABEL: str = "Sin correo"
