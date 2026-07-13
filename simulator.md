# ESPECIFICACIONES TÉCNICAS DEFINITIVAS DEL SIMULADOR

Este documento constituye la única fuente de verdad (*Single Source of Truth*) para los límites, umbrales, estados iniciales y comportamiento físico ante fallas del simulador.

---

## TABLA DE CONTENIDOS

1. [Visión General del Sistema](#1-visión-general-del-sistema)
2. [Diccionario de Sensores y Unidades](#2-diccionario-de-sensores-y-unidades)
3. [Arquitectura y Ciclo de Simulación](#3-arquitectura-y-ciclo-de-simulación)
4. [Física de la Bomba (Operación Normal)](#4-física-de-la-bomba-operación-normal)
5. [Máquina de Estados del Elevador](#5-máquina-de-estados-del-elevador)
6. [Matriz de Control: Estados Iniciales, Límites y Umbrales](#6-matriz-de-control-estados-iniciales-límites-y-umbrales)
7. [Clasificación de Riesgo y Motor de Alertas](#7-clasificación-de-riesgo-y-motor-de-alertas)
8. [Matriz de Inyección de Fallas (Valores Exactos)](#8-matriz-de-inyección-de-fallas-valores-exactos)
9. [Recuperación Progresiva Post-Falla](#9-recuperación-progresiva-post-falla)
10. [Sistema de Override Manual y Puentes a Fallas](#10-sistema-de-override-manual-y-puentes-a-fallas)
11. [API de Control de Simulación](#11-api-de-control-de-simulación)
12. [Base de Datos y Flujo de Datos](#12-base-de-datos-y-flujo-de-datos)

---

## 1. VISIÓN GENERAL DEL SISTEMA

**INES (Sistema Inteligente en Monitoreo)** es una aplicación Django que simula y monitorea sistemas de bombas y elevadores en edificios, con generación de datos de sensores en tiempo real, inyección de fallas, alertas por email y un dashboard web con streaming SSE.

### Stack Tecnológico
- **Backend:** Django + PostgreSQL (`monitoreo_db`)
- **Tiempo real:** Server-Sent Events (SSE) con eventlet
- **Reportes:** fpdf2 para generación de PDFs
- **Email:** SMTP (Gmail) con templates HTML estilo brutalist

### Flujo General de Datos
```
server.py / manage.py
  → Lee MonitoringEquipment de DB
  → Crea instancias BuildingSimulator (1 por edificio)
  → Spawn motor de simulación en greenlet eventlet
  → Cada 1 segundo: genera datos → clasifica riesgo → envía alertas → emite SSE
  → Browser consume SSE → renderiza dashboard en tiempo real
```

---

## 2. DICCIONARIO DE SENSORES Y UNIDADES

### Sistema de la Bomba

| Variable | ID | Unidad | Tipo |
|---|---|---|---|
| Caudal | `pump_flow_rate` | `l/s` | Rango continuo |
| Presión | `pump_pressure` | `bar` | Rango continuo |
| Temperatura | `pump_temperature` | `°C` | Rango continuo |
| Vibración | `pump_vibration` | `mm/s` | Rango continuo |
| Nivel de tanque | `pump_tank_level` | `%` | Rango continuo 0–100 |
| Voltaje | `pump_voltage` | `V` | Monofásico comercial (~220V) |
| Corriente | `pump_current` | `A` | Rango continuo |
| Calidad de agua | `pump_water_quality` | `ppm` | Rango continuo |

### Sistema del Elevador

| Variable | ID | Unidad | Tipo |
|---|---|---|---|
| Posición | `elev_position` | `piso` | Discreto 0.0 a 5.0 |
| Velocidad | `elev_speed` | `m/s` | Rango continuo |
| Carga | `elev_load` | `kg` | Rango continuo |
| Estado de puerta | `elev_door_status` | — | Enum: `closed`, `opening`, `open`, `closing` |
| Temperatura | `elev_temperature` | `°C` | Rango continuo |
| Vibración | `elev_vibration` | `mm/s` | Rango continuo |
| Voltaje | `elev_voltage` | `V` | Trifásico industrial (~380V) |
| Corriente | `elev_current` | `A` | Rango continuo |

---

## 3. ARQUITECTURA Y CICLO DE SIMULACIÓN

### Ciclo de Vida del Simulador

1. **Inicio:** Los simuladores arrancan en estado **pausado** (`sim_paused=True`).
2. **Arranque:** El usuario hace clic en "Start" vía dashboard → endpoint `sim_pause` → `sim_paused=False`.
3. **Tick de simulación:** Cada **1 segundo** (`SIM_TICK_INTERVAL=1`), el motor ejecuta `_run_sim_tick()` para cada edificio.
4. **Cada tick ejecuta:**
   - `_update_pump()` o `_update_elevator()` → genera nuevos valores físicos
   - `classify_risk()` → clasifica cada sensor en Normal/Alto/Crítico
   - Procesamiento de alertas con debounce (3 ticks consecutivos requeridos)
   - Construcción de registros de historial
5. **Emisión SSE:** Los datos se emiten vía SSE al navegador en cada tick.

### Constantes Físicas Clave

| Constante | Valor | Descripción |
|---|---|---|
| `PUMP_P0` | 7.0 bar | Presión base (caudal=0) |
| `PUMP_K` | 0.012 | Coeficiente de pérdida cuadrática |
| `CRUISING_SPEED` | 1.0 m/s | Velocidad crucero del elevador |
| `FLOOR_HEIGHT` | 4.0 m | Altura entre pisos |
| `JERK` | 0.5 m/s³ | Limitación de sacudida (perfil S) |
| `EMPTY_CABIN_MASS` | 800 kg | Masa vacía de la cabina |
| `COUNTERWEIGHT_MASS` | 1025 kg | Masa del contrapeso |
| `RATED_MOTOR_POWER` | 15000 W | Potencia nominal del motor |
| `RATED_CURRENT` | 28.3 A | Corriente nominal del motor |
| `DRIVE_EFFICIENCY` | 0.85 | Eficiencia del variador |
| `AMBIENT_TEMP` | 25.0 °C | Temperatura ambiente |
| `GRACE_TICKS` | 5 | Ticks de gracia al arrancar bomba |

---

## 4. FÍSICA DE LA BOMBA (OPERACIÓN NORMAL)

**Punto de entrada:** `_update_pump()` en `apps/sensors/simulation/physics/pump.py`

### Árbol de Decisión por Tick

```
¿Bomba encendida?
├── NO → _set_pump_idle(): flow=0, pressure=0, vibration=0, current=0,
│         temp converge a 22°C (tasa 0.5*dt), voltage converge a 220V,
│         water_quality random walk ~200ppm
├── SÍ, ¿hay falla activa? → _apply_pump_fault(): dispatch a handler específico
├── SÍ, ¿grace ticks > 0? → Decrementa grace (5 ticks después de arrancar)
└── SÍ, nada de lo anterior → _run_pump_normal()
```

### Cálculo de Sensores en Operación Normal

#### 1. Voltaje
```python
volt = prev + (220 - prev) * 0.05 * dt + uniform(-0.5, 0.5) * dt
```
Converge a 220V con ruido pequeño. Si cae por debajo de 50V, todos los outputs decaen rápidamente.

#### 2. Régimen de Estrella (tank < 10%)
Si el nivel del tanque es bajo:
- Caudal disminuye (`-3.0*dt`, mínimo 2.0)
- Presión cae (`-0.8*dt`, piso 1.0)
- Vibración sube (`+1.2*dt`)
- Temperatura sube (`+2.0*dt`)
- Corriente cae (`-2.0*dt`)

#### 3. Régimen Normal

**Caudal (flow_rate):**
```python
target = high_thresh * 0.85  # ~15.3 l/s con umbrales default
demand = random_walk(prev, center=target, range=[target-5, target])
flow = clamp(demand, ramp=3.0*dt)
```
El caudal opera típicamente entre `12.0–16.0 l/s`.

**Presión (pressure):**
```python
pressure = max(0.5, P0 - K * flow²) + noise
# Ejemplo: flow=14 → pressure = 7.0 - 0.012*(196) = 4.65 bar
```
Relación cuadrática presión-caudal. Ramp-limited a `1.5*dt`.

**Temperatura (temperature):**
```python
target_temp = 50.0 + (flow * pressure * 0.1)
# Ejemplo: 50 + (14 * 4.65 * 0.1) = 56.5°C
temp += (target - temp) * 0.02 * dt + noise
```
Modelo térmico de primer orden. Converge a ~45°C en régimen.

**Vibración (vibration):**
```python
vibration = 0.5 + flow/25.0 + max(0, temp-65)/40.0 + noise
# Base: 0.5 + flow component + temperatura component
```
Típico: `~1.5 mm/s`.

**Corriente (current):**
```python
current = (flow * pressure * 28.0 + pressure * 120.0) / (volt * 0.85) + noise
# Ejemplo: (14*4.65*28 + 4.65*120) / (220*0.85) = (1822.8 + 558) / 187 ≈ 12.7A
```
Calibrado para ~13A a 13 l/s, 5 bar, 220V.

**Calidad de agua (water_quality):**
```python
qual += (200 - qual) * 0.05 * dt + noise
```
Converge a 200ppm.

#### 4. Clamp de Seguridad (sin falla)
Todos los sensores operativos se limitan al **95% del umbral Alto** para evitar falsos alertas en operación normal:
- `pressure` → clamp a `high_thresh * 0.95`
- `temperature` → clamp a `high_thresh * 0.95`
- `vibration` → clamp a `high_thresh * 0.95`
- `current` → clamp a `high_thresh * 0.95`

### Física del Tanque

```python
inflow = pump_flow_rate  # si bomba encendida, else 0
outflow = average(target_max, target_min) + noise  # demanda del edificio
net = inflow - outflow
d_tank = net * 0.05 * dt + noise
tank_level = clamp(tank_level + d_tank, safe_bounds)
```

---

## 5. MÁQUINA DE ESTADOS DEL ELEVADOR

**Punto de entrada:** `_update_elevator()` en `apps/sensors/simulation/physics/elevator.py`

El elevador opera con una **máquina de estados finitos (FSM)** de 7 estados:

```
IDLE → DOOR_OPENING → DOORS_OPEN → DOOR_CLOSING → ACCELERATING → MOVING → DECELERATING → (loop)
```

### Transiciones por Estado

#### 1. IDLE (Idle)
- **Espera:** 2–5 segundos aleatorios
- **Acción:** Selecciona piso destino aleatorio (diferente al actual), calcula dirección
- **Sensores:** speed=0, door=closed
- **Transición:** → DOOR_OPENING

#### 2. DOOR_OPENING (Abriendo puerta)
- **Door status:** `"opening"`, speed=0
- **Duración:** `DOOR_OPEN_TIME / sim_speed` (2.0s default)
- **Transición:** → DOORS_OPEN

#### 3. DOORS_OPEN (Puertas abiertas)
- **Door status:** `"open"`, speed=0
- **Duración:** 8 ticks (tiempo para pasajeros)
- **Acción:** La carga cambia aleatoriamente `-150` a `+150 kg`
- **Transición:** → DOOR_CLOSING

#### 4. DOOR_CLOSING (Cerrando puerta)
- **Door status:** `"closing"`, speed=0
- **Verificación de sobrecarga:** Si carga efectiva > 800kg → bloquea y reabre puertas (speed=0, current=0)
- **Duración:** `DOOR_CLOSE_TIME / sim_speed` (2.0s default)
- **Transición:** → ACCELERATING (o IDLE si ya está en piso destino)

#### 5. ACCELERATING (Acelerando — Perfil S)
```python
acceleration += JERK * torque_factor * dt
acceleration = min(acceleration, ACCELERATION * torque_factor)
speed += acceleration * dt
position += (prev_speed + speed) / 2 * direction * dt * traction_factor
```
- **Transición:** → MOVING cuando speed >= 90% de `CRUISING_SPEED`
- Si `torque_factor=0` (motor atascado), speed queda en 0

#### 6. MOVING (Crucero)
- Mantiene speed ~`1.0 m/s` con ruido pequeño
- Si `governor_failed=True`: acelera a `0.5 m/s²`
- Calcula distancia de frenado; → DECELERATING cuando está en rango

#### 7. DECELERATING (Frenando — Perfil S)
```python
acceleration -= JERK * torque_factor * dt
speed = max(0, speed + acceleration * dt)
```
- Cuando speed <= 0.05: snaps posición al piso más cercano → DOOR_OPENING

### Cálculo de Sensores Post-FSM (cada tick)

**Posición:**
```python
elev_position = position_meters / FLOOR_HEIGHT
# En estados estacionarios: snap a entero
```

**Temperatura del motor (modelo térmico):**
```python
target_temp = 25 + (effective_load/500)*20 + |speed|*5 + 5*(acceleration)
motor_temp += (target - motor_temp) * 0.03 * dt + noise
# Típico en crucero: ~40–50°C
```

**Voltaje:**
```python
base = 380V + uniform(-5, 5)
# Durante aceleración: -12V
# Con pérdida de tracción: -8V
# Con corte de energía: 0V
```

**Vibración:**
```python
# IDLE: 0.5
# Movimiento: 1.0 + |speed| * 0.8 + noise
# Con pérdida de tracción: +8.5 + noise
```

**Corriente (modelo eléctrico complejo):**
```python
# IDLE: rated_current * 0.08 (~2.2A)
# Operación de puertas: rated_current * 0.12 (~3.4A)
# Movimiento: modelo físico completo:
total_mass = EMPTY_CABIN_MASS + load  # 800 + carga
unbalance = (total_mass - COUNTERWEIGHT_MASS) * G  # (800+carga - 1025) * 9.81
motor_force = unbalance * direction + total_mass * acceleration
mechanical_power = motor_force * speed
electrical_power = mechanical_power / efficiency / 1000
base_current = rated * (0.3 + load_ratio * 0.7)
# Inrush current: hasta 2.5x en primeros 0.5s de aceleración, decae linealmente
```

---

## 6. MATRIZ DE CONTROL: ESTADOS INICIALES, LÍMITES Y UMBRALES

### Sistema: BOMBA

**Arranque Seguro (Time Step 0):**
```
flow=0.0, pressure=1.0, temp=25.0, vibration=0.0,
tank=50.0, voltage=220.0, current=0.0, water_quality=150.0
```

**Control de bomba:** La bomba se controla **únicamente de forma manual**. No existe float switch automático por nivel de tanque.

| Sensor | Límite Mín | Límite Máx | Umbral Normal | Umbral Alto | Umbral Crítico |
| --- | --- | --- | --- | --- | --- |
| `pump_flow_rate` | — | — | 0.0 a 18.0 | > 18.0 | > 22.0 |
| `pump_pressure` | 0.0 | 10.0 | 1.0 a 6.0 | > 6.0 | > 8.0 ó < 0.5 |
| `pump_temperature` | 22.0 *(T\_AMB)* | 100.0 | 22.0 a 60.0 | > 60.0 | > 85.0 |
| `pump_vibration` | 0.0 | 15.0 | 0.0 a 4.5 | > 4.5 | > 7.1 |
| `pump_tank_level` | 0.0 | 100.0 | 20.0 a 90.0 | > 90.0 ó < 20.0 | > 95.0 ó < 10.0 |
| `pump_voltage` | 0.0 | 300.0 | 210.0 a 230.0 | Fuera de Normal | > 242.0 ó < 198.0 |
| `pump_current` | 0.0 | 30.0 | 0.0 a 16.0 | > 16.0 | > 22.0 |
| `pump_water_quality` | — | — | 0.0 a 300.0 | > 300.0 | > 500.0 |

### Sistema: ELEVADOR

**Arranque Seguro (Time Step 0):**
```
position=0.0, speed=0.0, load=0.0, door_status=0.0,
temp=25.0, vibration=0.0, voltage=380.0, current=0.0
```

| Sensor | Límite Mín | Límite Máx | Umbral Normal | Umbral Alto | Umbral Crítico |
| --- | --- | --- | --- | --- | --- |
| `elev_position` | 0.0 | 5.0 | — | — | — |
| `elev_speed` | 0.0 | 3.0 | 0.0 a 1.2 | > 1.2 | > 1.6 |
| `elev_load` | 0.0 | 1200.0 | 0.0 a 600.0 | > 600.0 | > 800.0 *(Bloqueo)* |
| `elev_door_status` | — | — | Abierta/Cerrando/Cerrada en parada son estados normales. Solo Crítico si abierta en movimiento. | — | — |
| `elev_temperature` | 22.0 *(T\_AMB)* | 90.0 | 22.0 a 60.0 | > 60.0 | > 80.0 |
| `elev_vibration` | 0.0 | 10.0 | 0.0 a 3.0 | > 3.0 | > 5.0 |
| `elev_voltage` | 0.0 | 500.0 | 360.0 a 400.0 | Fuera de Normal | > 418.0 ó < 342.0 |
| `elev_current` | 0.0 | 40.0 | 0.0 a 25.0 | > 25.0 | > 35.0 |

### Comportamiento Dinámico en Línea Base (Sin Fallas)

- **Bomba Activa:** Caudal `~12.0–16.0 l/s`, presión `~3.5 bar`, corriente `~13.0 A`. La temperatura asciende paulatinamente hasta estabilizarse en `~45.0 °C`. Vibración residual de `~1.5 mm/s`.
- **Bomba Apagada:** Todos los valores operativos caen a 0. Temperatura converge a `22.0 °C` (temperatura ambiente). Voltaje se mantiene en `~220 V` (red disponible).
- **Elevador Activo:** Pico transitorio de corriente al arrancar, estabilizándose en `~12.0–18.0 A` en régimen crucero (`1.0 m/s`). Temperatura del motor `~40–50 °C`. Cambios de posición continuos y lineales.

---

## 7. CLASIFICACIÓN DE RIESGO Y MOTOR DE ALERTAS

### Función `classify_risk()`

Ubicada en `apps/core/services/risk_service.py`. Toma una variable, valor, diccionario de umbrales y fallas activas. Retorna `(risk_level, color)`.

#### Lógica de Clasificación

1. **Riesgo forzado por falla:** Si `(fault_type, variable)` está en `FAULT_FORCED_RISK`, retorna ese riesgo inmediatamente. Actualmente: `("door_blocked", "elev_door_status")` y `("pos_sensor_fail", "elev_door_status")` → Crítico.

2. **Sensores booleanos:** True → Crítico, False → Normal.

3. **Sensores enum** (`elev_door_status`): Valores en `ENUM_RISK_VALUES` → Crítico (actualmente vacío, no genera alertas automáticas).

4. **Sensores sin riesgo:** `elev_position` → siempre Normal.

5. **Sensores de rango** (pressure, tank_level, voltage):
   - Dentro de `[high_low, high_high]` → Normal
   - Entre límites críticos y normales → Alto
   - Fuera de límites críticos (`crit_low` o `crit_high`) → Crítico

6. **Sensores de dirección "higher"** (flow, temperature, vibration, current, speed, load, water_quality):
   - `<= high` → Normal
   - `<= critic` → Alto
   - `> critic` → Crítico

### Motor de Alertas

#### Debounce (Anti-falsos positivos)
- **`ALERT_DEBOUNCE_TICKS = 3`:** Un sensor debe estar en Alto o Crítico durante **3 ticks consecutivos** antes de que se dispare una alerta.
- **Exclusiones:** Variables bajo override manual, o variables de bomba durante los 5 ticks de gracia de arranque.

#### Cooldown (Anti-spam)
- **`COOLDOWN_SECONDS = 1800`** (30 minutos): No se envían emails duplicados para la misma variable dentro de esta ventana.

#### Alertas Compuestas
- Cuando una falla está activa, se envía **UNA alerta compuesta por tipo de falla** (no por variable), agrupando todos los sensores afectados.
- Manejado por `_send_compound_alerts_for_faults()`.

#### Persistencia
- Las alertas se guardan en la tabla `historial` con: usuario, equipo de monitoreo, fecha, mensaje (JSON), tipo_falla, variables_afectadas (JSON).
- Al resolver una alerta: se marca `resuelto=True` y se envía email de resolución.

---

## 8. MATRIZ DE INYECCIÓN DE FALLAS (VALORES EXACTOS)

**NOTA IMPORTANTE:** Al inyectarse una falla, los sensores saltan de **forma directa e instantánea** a los valores anómalos, sin rampas progresivas. Esto está diseñado así para facilitar pruebas y validación inmediata del sistema de alertas.

### Reglas Generales de Inyección
- Las fallas **solo se pueden inyectar** cuando el dispositivo está **encendido** (`pump_on`/`elevator_on=True`). Si no, se retorna HTTP 409 (`DeviceOffError`).
- Al **limpiar** una falla, se activa recuperación progresiva de 15 segundos.
- Al **apagar** un dispositivo, se limpian automáticamente todas sus fallas activas.

---

### Inyecciones en Bomba (8 tipos)

#### 1. Sequía (Dry Run) — `dry_run`
| Sensor | Valor |
|---|---|
| `tank_level` | **0.0%** |
| `flow_rate` | **0.0** |
| `pressure` | **0.0** |
| `current` | **0.0** |
| `temperature` | **90.0°C** |
| `vibration` | **10.0 mm/s** |

#### 2. Descarga Bloqueada — `blocked_discharge`
| Sensor | Valor |
|---|---|
| `flow_rate` | **0.0** |
| `pressure` | **10.0 bar** (máximo) |
| `vibration` | **10.0 mm/s** |
| `temperature` | **90.0°C** |
| `current` | **25.0 A** |
| `tank_level` | **Sube lentamente** (+0.1*dt) |

#### 3. Ruptura de Tubería — `pipe_burst`
| Sensor | Valor |
|---|---|
| `flow_rate` | **50.0 l/s** (máximo) |
| `pressure` | **0.0** |
| `vibration` | **10.0 mm/s** |
| `current` | **25.0 A** |
| `temperature` | **90.0°C** |
| `tank_level` | **0.0%** |

#### 4. Cavitación — `cavitation`
| Sensor | Valor |
|---|---|
| `flow_rate` | **random(25–35)** |
| `vibration` | **10.0 mm/s** |
| `pressure` | **random(0–0.5)** |
| `temperature` | **90.0°C** |
| `current` | **random(25–30)** |

#### 5. Sobrecalentamiento — `overheat`
| Sensor | Valor |
|---|---|
| `temperature` | **100.0°C** (máximo físico) |
| `vibration` | **10.0 mm/s** |
| `current` | **25.0 A** |
| `flow_rate` | **0.0** |

#### 6. Sobrecarga Eléctrica — `power_surge`
| Sensor | Valor |
|---|---|
| `flow_rate` | **0.0** |
| `pressure` | **0.0** |
| `voltage` | **300.0 V** (máximo) |
| `current` | **30.0 A** (máximo) |
| `temperature` | **90.0°C** |
| `vibration` | **10.0 mm/s** |

#### 7. Corte Eléctrico — `power_outage`
| Sensor | Valor |
|---|---|
| `voltage` | **0.0** |
| `current` | **0.0** |
| `flow_rate` | **0.0** |
| `pressure` | **0.0** |
| `vibration` | **0.0** |
| `temperature` | **22.0°C** (ambiente) |

#### 8. Falla de Rodamientos — `bearing_failure`
| Sensor | Valor |
|---|---|
| `vibration` | **10.0 mm/s** (crítico) |
| `temperature` | **90.0°C** (crítico) |
| `current` | **25.0 A** (fricción parásita) |
| `water_quality` | **600.0 ppm** (contaminación) |
| `flow_rate` | **0.0** |
| `pressure` | **0.0** |

---

### Inyecciones en Elevador (7 tipos)

Las fallas del elevador **modifican parámetros físicos** que la FSM consume. Luego se force-sobreescriben telemetrías.

#### 1. Motor Atascado — `motor_stuck`
| Parámetro físico | Telemetría forzada |
|---|---|
| `torque_factor = 0.0` | `speed = 0.0` |
| | `current = 40.0 A` (máximo rotor bloqueado) |
| | `door_status = "closed"` |
| | `temperature = 110.0°C` |
| | `vibration = 9.5 mm/s` |
| | `voltage = 355.0 V` |
| | Estado FSM: `"STUCK"` |

#### 2. Puerta Bloqueada — `door_blocked`
| Parámetro físico | Telemetría forzada |
|---|---|
| `door_obstructed = True` | `door_status = "open"` |
| | `speed = 0.0` |
| | `current = 0.0` |
| | Estado FSM: `"DOORS_OPEN"` |

#### 3. Exceso de Velocidad — `overspeed`
| Parámetro físico | Telemetría forzada |
|---|---|
| `governor_failed = True` | `speed = 2.0 m/s` |
| `brake_failed = True` | `current = 5.0 A` |
| | `door_status = "closed"` |
| | `temperature = 80.0°C` |
| | `vibration = 6.5 mm/s` |
| | Estado FSM: `"MOVING"` |

#### 4. Sobrecarga — `overload`
| Parámetro físico | Telemetría forzada |
|---|---|
| `overload_extra_kg = 900.0` | `load = 1020.0 kg` (máximo*0.85) |
| | `door_status = "open"` |
| | `speed = 0.0` |
| | `current = 0.0` |
| | Estado FSM: `"DOORS_OPEN"` |

#### 5. Fallo de Sensor de Posición — `pos_sensor_fail`
| Parámetro físico | Telemetría forzada |
|---|---|
| `pos_sensor_stuck = True` | `position = congelado en piso de inyección` |
| | `speed = 1.0 m/s` |
| | `door_status = "closed"` |
| | Estado FSM: `"MOVING"` |
| | **Parada de emergencia en ≤ 1 tick** |

#### 6. Corte de Energía Comercial — `commercial_power_outage`
| Parámetro físico | Comportamiento |
|---|---|
| `power_available = False` | **Fase 1** (<0.1s): speed=0, door="closed", current=0 (freno) |
| `torque = 0` | **Fase 2** (0.1–3s): speed=0, IDLE |
| | **Fase 3** (>3s): batería de emergencia → 0.3 m/s al piso más cercano → door="open" |

#### 7. Pérdida de Tracción — `traction_loss`
| Parámetro físico | Telemetría forzada |
|---|---|
| `traction_loss = True` | `vibration = 12.0 mm/s` |
| | `current = rated * 0.2 (~5.6A)` |
| | `temperature = 95.0°C` |
| | `speed = 1.0 m/s` (motor gira, cabina no) |
| | Factor de posición: **0.1** (10% de normal) |

---

## 9. RECUPERACIÓN PROGRESIVA POST-FALLA

**Archivo:** `apps/sensors/simulation/fault_recovery.py`

Al limpiar una falla, los sensores **no saltan instantáneamente** a valores normales. En su lugar, usan un sistema de `manual_overrides` con rampas progresivas:

- **Duración:** 15 segundos
- **Tasa máxima de cambio:** `MAX_STEPS_PER_SECOND` por sensor
- **Mecanismo:** Cada tick se calcula la dirección hacia el valor normal y se aplica un paso limitado

### Proceso de Limpieza de Falla
1. Se desactiva la falla en el estado del simulador
2. Se marcan como `resueltos` los registros de historial relacionados
3. Se envían emails de resolución a suscriptores
4. Se limpian cooldowns y alertas pendientes
5. Se inicia la recuperación progresiva de 15 segundos

---

## 10. SISTEMA DE OVERRIDE MANUAL Y PUENTES A FALLAS

**Archivo:** `apps/sensors/simulation/simulation_engine.py`

El sistema permite al administrador forzar valores de sensores manualmente vía la API. Existe un mecanismo que detecta si un override manual debe activar automáticamente una falla:

### Puentes Automáticos (Override → Falla)

| Condición del Override | Falla Activada |
|---|---|
| `pump_voltage` forzado < 10V | `power_outage` (Corte eléctrico) |
| `elev_load` forzado > 900kg | `overload` (Sobrecarga) |

### Reglas de Override
- Variables bajo override manual quedan **excluidas** del motor de alertas (no generan falsos positivos)
- El override persiste hasta que se limpie manualmente o se haga reset del simulador
- Se puede verificar si una variable está bajo override con `is_locked(variable)`

---

## 11. API DE CONTROL DE SIMULACIÓN

### Endpoints Principales

| Método | URL | Descripción | Auth |
|---|---|---|---|
| `POST` | `/api/sim/<id>/pause/` | Pausar/reanudar simulación | Admin |
| `POST` | `/api/sim/<id>/reset/` | Resetear simulador a valores iniciales | Admin |
| `POST` | `/api/sim/<id>/inject-fault/` | Inyectar falla `{device, fault_type}` | Admin |
| `POST` | `/api/sim/<id>/clear-fault/` | Limpiar falla `{device?}` | Admin |
| `POST` | `/api/sim/<id>/set-speed/` | Velocidad de simulación `{speed: 0.1–10}` | Admin |
| `POST` | `/api/sim/<id>/toggle-pump/` | Encender/apagar bomba `{on?}` | Admin |
| `POST` | `/api/sim/<id>/toggle-elevator/` | Encender/apagar elevador `{on?}` | Admin |
| `GET` | `/api/sim/<id>/status/` | Estado actual del simulador | Login |
| `GET` | `/sse/<building_id>/` | Stream SSE de datos en vivo | — |
| `GET` | `/api/status/` | Payload completo en vivo (JSON) | — |

### Dashboard Features
- Datos de sensores en tiempo real via SSE (actualización cada 1 segundo)
- Indicadores de riesgo por color (verde/naranja/rojo)
- Controles de encendido/apagado de bomba y elevador
- Control de velocidad de simulación (0.1x – 10x)
- Panel de inyección de fallas con las 15 fallas disponibles
- Selector de edificio para alternar entre monitoreos
- Estadísticas en vivo (mín/máx/promedio por sensor)
- Log de alertas desde la base de datos

---

## 12. BASE DE DATOS Y FLUJO DE DATOS

### Tablas Principales

| Tabla | Modelo | Columnas Clave |
|---|---|---|
| `edificio` | `Building` | `id_edificio` (PK), `nb_edificio`, `rif` (unique), `direccion`, `cantidad_pisos` |
| `equipo_monitoreo` | `MonitoringEquipment` | `id_equipo_monitoreo` (PK), `nb_equipo`, `id_edificio` (FK), `tipo` (bomba/elevador), `status` (operativo/falla/mantenimiento) |
| `usuario_edificio` | `UserBuilding` | `id_asignacion` (PK), `id_usuario` (FK), `id_edificio` (FK) |
| `persona` | `Persona` | `id_persona` (PK), `ci` (unique), `primer_nombre`, `email` (unique) |
| `usuario` | `Usuario` | `id_usuario` (PK), `username` (unique), `password`, `rol` (US/SA) |
| `historial` | `History` | `id_historial` (PK), `id_usuario` (FK), `id_equipo_monitoreo` (FK), `fecha`, `mensaje` (JSON), `resuelto`, `tipo_falla`, `variables_afectadas` (JSON) |
| `umbral_config` | `ThresholdConfig` | `id_edificio` (FK), `variable`, `direction`, `high`, `critic` |
| `limite_sensor_config` | `SensorLimitConfig` | `id_edificio` (FK), `variable`, `max_value` |

### Flujo Completo de Datos

```
1. server.py lee MonitoringEquipment de DB
2. Crea instancias BuildingSimulator en el dict global `simulators`
3. Motor de simulación arranca en greenlet eventlet
4. Cada 1 segundo:
   a. _run_sim_tick() genera nuevos valores físicos
   b. classify_risk() clasifica cada sensor
   c. Motor de alertas verifica debounce + cooldown
   d. Si hay alerta: persiste en `historial` + envía email
   e. Payload se emite vía SSE al navegador
5. Browser consume SSE → actualiza dashboard en tiempo real
6. Límites y umbrales son configurables por edificio vía admin UI
```

### Configuración por Edificio
- **Umbrales (`umbral_config`):** Cada edificio puede tener umbrales personalizados por variable, stored como `(direction, high, critic)`.
- **Límites de sensores (`limite_sensor_config`):** Cada edificio puede sobrescribir el `max_value` de cada sensor.
- Se sincronizan automáticamente con el simulador cuando se actualizan desde la UI.

---

## REGLAS DE DISEÑO CLAVE

1. **Sin control automático de bomba:** No hay float switch. La bomba se controla exclusivamente manual.
2. **Clamp de seguridad en operación normal:** Todos los sensores se limitan al 95% del umbral Alto para nunca generar falsos alertas.
3. **Fallas instantáneas:** Las fallas fuerzan valores de inmediato (diseñado para testing).
4. **Recuperación progresiva:** Al limpiar falla, sensores rampan suavemente por 15 segundos.
5. **Override manual puentea fallas:** Forzar ciertos valores activa automáticamente la física de falla correspondiente.
6. **Sobrecarga bloquea a 800kg:** El elevador físicamente no puede cerrar puertas ni moverse.
7. **Rescate por batería:** En corte de energía, el elevador frena (0.1s), espera batería (3s), luego va al piso más cercano a 0.3 m/s.
8. **Sensor de posición defectuoso → parada de emergencia:** Detección en ≤ 1 tick.
9. **Backoff exponencial en errores:** Si un tick falla, espera 2^n ticks (máx 30) antes de reintentar.
