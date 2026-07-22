# Funcionamiento del Sistema de Fallas en el Simulador

Este documento detalla la arquitectura, el flujo y el comportamiento del sistema de fallas implementado en el simulador (Bomba de Agua y Elevador). Explica cómo interactúa la interfaz de usuario con el backend y cómo impactan estas fallas en las variables físicas y eléctricas de los equipos según los principios de la ingeniería real.

---

## 1. Interfaz de Usuario (Frontend)

El selector de fallas se encuentra en la plantilla del panel de control: `monitoring_dashboard.html`.

### Elementos Principales

* **Selectores HTML**: Existen dos menús desplegables (`<select>`), uno para la bomba (`id="simFaultPump"`) y otro para el elevador (`id="simFaultElevator"`).
* **Controlador JavaScript (`SimulationController`)**: El frontend escucha los cambios en estos selectores mediante el evento `change`. Cuando el usuario selecciona una falla o la opción "Ninguna", se ejecuta el método `_handleFaultChange(device, newFault)`.

### Comunicación con el API

* **Inyectar falla**: Si se selecciona una falla (ej. `dry_run`), se hace una petición `POST` al endpoint `/api/sim/{ID_EDIFICIO}/inject-fault/` con un payload JSON: `{"device": "pump", "fault_type": "dry_run"}`.
* **Limpiar falla**: Si se selecciona "Ninguna", se hace una petición `POST` a `/api/sim/{ID_EDIFICIO}/clear-fault/` con el payload: `{"device": "pump"}`.

Además, existe sincronización en tiempo real mediante *Server-Sent Events (SSE)*. Si una falla se dispara automáticamente o se limpia desde otro cliente, la función `syncFromPayload` del frontend actualiza el selector para reflejar el estado exacto en el backend.

---

## 2. Lógica de Backend (Controladores)

Las llamadas de la API son procesadas en `apps/dashboard/simulation/controls.py`.

* **`sim_inject_fault`**: Llama al núcleo de control del simulador. Primero limpia cualquier falla existente y luego inyecta la nueva. Además, reinicia el temporizador de "gracia de protección" para que el equipo no se apague inmediatamente si la protección está encendida.
* **`sim_clear_fault`**: Limpia la falla solicitada.

### Núcleo de Simulación (`apps/sensors/simulation/controls.py`)

* Al inyectar la falla (`inject_fault`), se guarda el tipo de falla en el estado del simulador (`sim.sim_faults[device] = fault_type`) y se registra el momento exacto (`sim.fault_injected_at`).
* **Transición**: Se inicia el estado `sim.fault_transition_pump = "injecting"` (o `elev`). Esto le indica al motor de físicas que aplique los efectos de la falla progresivamente (siguiendo curvas de respuesta temporal de primer u orden superior) y no de forma instantánea no natural.
* Al limpiar la falla (`clear_fault`), se limpia del estado del simulador y se pasa al estado `recovering` (`sim.fault_transition = "recovering"`), lo cual indica al motor que regrese los valores a la normalidad de forma suave, permitiendo que las alertas previas sean marcadas como resueltas en el historial (`History`).

---

## 3. Tipos de Fallas y Variables Afectadas

Cada falla está configurada en `apps/sensors/sensor_config.py` y afecta un subconjunto específico de sensores para imitar con fidelidad técnica el comportamiento físico y eléctrico.

### Bomba de Agua centrífuga

Cada falla inyectada en la bomba altera la simulación física (en `apps/sensors/simulation/physics/pump.py`) aplicando las leyes hidráulicas y la relación de potencia $P \propto Q \cdot H$:

| Falla | Identificador | Comportamiento Físico y Matemático Real | Sensores afectados |
| --- | --- | --- | --- |
| **Sequía (Trabajo en seco)** | `dry_run` | El tanque de succión se vacía ($0\%$). Al no haber fluido en la cámara, $Q=0$ y $P=0$. El motor gira prácticamente sin carga hidráulica, cayendo la corriente a consumo en vacío ($I \approx 30\%$ de $I_{nom}$). Sin fluido para lubricar y disipar calor, el sello mecánico genera fricción seca, elevando la temperatura ($+30\%$ sobre crítico). La turbulencia de aire genera vibración desbalanceada ($+20\%$). El nivel del tanque de descarga se congela. | Caudal, Presión, Temperatura, Vibración, Nivel succión, Corriente |
| **Descarga bloqueada** | `blocked_discharge` | Válvula de salida cerrada ($Q=0$). La bomba opera en el punto de corte (*Shut-off head*), llevando la presión a su máximo estático ($+30\%$ sobre crítico). En bombas centrífugas, a caudal cero la potencia consumida es mínima, bajando la corriente a $\approx 50-60\%$ de $I_{nom}$. La energía mecánica remanente se disipa como calor en el agua atrapada, haciendo ebullir el líquido en la carcasa e incrementando la temperatura exponencialmente ($+45\%$ sobre crítico) y generando cavitación por ebullición. | Caudal, Presión, Temperatura, Vibración, Corriente |
| **Ruptura de tubería** | `pipe_burst` | Pérdida repentina de contrapresión (zona de *Runout*). El caudal se dispara al máximo ($+40\%$ sobre crítico) y la presión colapsa a $\approx 0\text{ bar}$. La demanda de mover este volumen descontrolado exige torque máximo al motor, provocando sobrecarga eléctrica severa ($I \approx +35\%$ sobre crítico). La turbulencia extrema en el punto de rotura eleva la vibración ($+25\%$) y la corriente sostenida eleva la temperatura del estator ($+20\%$). | Caudal, Presión, Vibración, Temperatura, Corriente, Nivel descarga |
| **Cavitación** | `cavitation` | Formación e implosión de microburbujas de vapor por baja presión de succión (NPSHa < NPSHr). Provoca fluctuaciones erráticas y ruidosas en el caudal y la presión. El choque de las implosiones genera picos extremos de vibración de alta frecuencia ($+50\%$ sobre crítico con alto *jitter*). La erosión genera micropartículas que incrementan ligeramente la turbidez a largo plazo. | Caudal, Presión, Vibración, Corriente, Calidad de agua |
| **Sobrecalentamiento** | `overheat` | Ascenso térmico directo por falla en ventilación o alta temperatura ambiente ($+25\%$ sobre crítico). La dilatación térmica reduce las holguras mecánicas de la bomba, incrementando el roce; esto produce una ligera sobrecorriente ($+8\%$), aumento de vibración ($+15\%$) y una degradación volumétrica progresiva del $10-15\%$ en caudal y presión. | Temperatura, Vibración, Corriente, Caudal, Presión |
| **Sobrecarga eléctrica / Rotor atascado** | `power_surge` | Bloqueo mecánico del eje o falla severa en el bobinado. El caudal y la presión caen a $0$ de forma instantánea. Al no haber rotación ($RPM=0$), la contra-fuerza electromotriz desaparece y la corriente se dispara a la corriente de rotor bloqueado ($LRA \approx 400-500\%$ de $I_{nom}$). Esto provoca una caída de tensión severa en la red (*Sag* en voltaje) y un calentamiento crítico del estator antes de que salte la protección térmica. | Caudal, Presión, Voltaje, Corriente, Temperatura |
| **Corte eléctrico** | `power_outage` | Pérdida total de suministro eléctrico. Voltaje, corriente, caudal, presión y vibración caen a $0$ inmediatamente. El nivel del tanque se congela. La temperatura del motor inicia un enfriamiento progresivo hacia la temperatura ambiente ($T_{amb} = 22^\circ\text{C}$) siguiendo la ley de enfriamiento de Newton: $T(t) = T_{amb} + (T_{actual} - T_{amb}) \cdot e^{-kt}$. | Todos (Pasan a 0; Temperatura enfriando progresivamente) |
| **Falla de rodamientos** | `bearing_failure` | Degeneración física de la pista/bolas del rodamiento. El aumento de fricción dispara las lecturas de vibración a valores críticos ($+40\%$) y eleva la temperatura localizada en la chumacera ($+20\%$). El torque de fricción adicional eleva ligeramente el consumo eléctrico ($I \approx +10\%$). La pérdida de alineación axial/radial causa una leve pérdida de eficiencia hidráulica en caudal y presión ($\approx 10\%$). | Vibración, Temperatura, Corriente, Caudal, Presión |

### Elevador

Las fallas del elevador se simulan en la máquina de estados y física (`apps/sensors/simulation/physics/elevator.py`):

| Falla | Identificador | Comportamiento Físico y Matemático Real | Sensores afectados |
| --- | --- | --- | --- |
| **Motor atascado** | `motor_stuck` | Rotor inmovilizado ($RPM=0$). Aceleración y velocidad caen a $0$. Se aplica corriente de rotor bloqueado ($I \approx 400\%$ sobre nominal), lo que genera caída de voltaje en red (Sag al $90\%$), aumento térmico acelerado en el estator ($+20\%$) y fuerte zumbido/vibración magnética ($+20\%$). | Temperatura, Velocidad, Corriente, Estado puerta, Voltaje, Vibración |
| **Puerta bloqueada** | `door_blocked` | Se activa la bandera de obstrucción física (`_elev_door_obstructed = True`). La lógica de seguridad impide el arranque del equipo mientras el contacto de seguridad de puerta esté abierto. El estado permanece en `open`, la velocidad se mantiene en $0$ m/s y el consumo eléctrico se limita a los circuitos de control. | Estado puerta, Velocidad, Corriente |
| **Exceso de velocidad** | `overspeed` | Falla en el control vectorial/freno dinámico. La cabina acelera superando la velocidad nominal por un $+20\%$ hasta alcanzar el umbral del gobernador de velocidad. Las fuerzas dinámicas e inerciales elevan la vibración ($+15\%$) y la temperatura de las guías y poleas por fricción. | Velocidad, Corriente, Estado puerta, Vibración |
| **Sobrecarga** | `overload` | Carga útil medida por pesacargas supera el $100\%$ de la capacidad nominal. El sistema de maniobra inhabilita el cierre de puertas y bloquea la orden de viaje (velocidad = $0$, motor sin energizar). Se activa señal auditiva/visual de sobrecarga. | Carga, Estado puerta, Velocidad, Corriente |
| **Fallo de sensor de posición** | `pos_sensor_fail` | Pérdida o congelamiento del conteo del encoder (`_elev_pos_stuck_value`). La lógica de control detecta una inconsistencia entre la velocidad real medida/ordenada y la variación nula de posición. Tras $1$ ciclo de simulación, el sistema ejecuta una parada de emergencia activando el freno electromecánico. | Posición, Velocidad, Estado puerta, Corriente |
| **Corte de energía comercial** | `commercial_power_outage` | Pérdida del suministro eléctrico principal ($V=0$). El freno electromecánico cae por falta de tensión deteniendo la cabina inmediatamente. Tras una retardo de seguridad, se activa el sistema de rescate automático por baterías (UPS), moviendo la cabina a velocidad reducida (`BATTERY_RESCUE_SPEED`) hacia el nivel más cercano para abrir puertas. | Voltaje, Corriente, Velocidad, Estado puerta, Temperatura |
| **Pérdida de tracción** | `traction_loss` | Deslizamiento de los cables sobre la polea de tracción por desgaste de gargantas o falta de adherencia. El motor gira a velocidad angular nominal y consume baja corriente (sin carga efectiva $\approx 30\%$), pero la velocidad lineal real de la cabina cae al $10\%$. La fricción del cable deslizante genera vibración e incremento térmico en poleas. | Posición, Velocidad, Corriente, Vibración, Temperatura |

---

## 4. Matriz de Verificación Detallada

Cada fila muestra la correspondencia exacta entre la especificación, la lista `FAULT_AFFECTED_VARIABLES` en `sensor_config.py`, las variables que modifica el handler de físicas, y los sensores mencionados en el `FAULT_ALERT_MESSAGES`.

### Bomba de Agua

#### `dry_run` — Sequía (Trabajo en seco)

| Capa | Sensores |
| --- | --- |
| **Spec** | Caudal, Presión, Temperatura, Vibración, Nivel succión, Corriente |
| **`FAULT_AFFECTED_VARIABLES`** | `pump_flow_rate`, `pump_pressure`, `pump_temperature`, `pump_vibration`, `pump_tank_level`, `pump_current` |
| **Handler `_apply_dry_run`** | `flow=0`, `pressure=0`, `tank=0%`, `temperature↑ (+15% sobre crítico)`, `vibration↑ (+25% sobre crítico)`, `current↓ (~3.5 A vacío)` |
| **Mensaje de alerta** | Caudal, presión, nivel de tanque, temperatura, vibración y corriente |
| **Estado** | ✅ Sincronizado |

#### `blocked_discharge` — Descarga bloqueada

| Capa | Sensores |
| --- | --- |
| **Spec** | Caudal, Presión, Temperatura, Vibración, Corriente |
| **`FAULT_AFFECTED_VARIABLES`** | `pump_flow_rate`, `pump_pressure`, `pump_vibration`, `pump_temperature`, `pump_current` |
| **Handler `_apply_blocked_discharge`** | `flow=0`, `pressure↑ (+25% shut-off head)`, `temperature↑ (+25% sobre crítico)`, `vibration↑ (+15% sobre crítico)`, `current↓ (~8.5 A)` |
| **Mensaje de alerta** | Caudal, presión, temperatura, vibración y corriente |
| **Estado** | ✅ Sincronizado |

#### `pipe_burst` — Ruptura de tubería

| Capa | Sensores |
| --- | --- |
| **Spec** | Caudal, Presión, Vibración, Temperatura, Corriente, Nivel descarga |
| **`FAULT_AFFECTED_VARIABLES`** | `pump_flow_rate`, `pump_pressure`, `pump_vibration`, `pump_temperature`, `pump_current`, `pump_tank_level` |
| **Handler `_apply_pipe_burst`** | `flow↑ (+30% runout)`, `pressure=0`, `current↑ (+15% sobre crítico)`, `vibration↑ (+20%)`, `temperature↑ (+15%)`, `tank=0%` |
| **Mensaje de alerta** | Caudal, presión, nivel de tanque, temperatura, vibración y corriente |
| **Estado** | ✅ Sincronizado |

#### `cavitation` — Cavitación

| Capa | Sensores |
| --- | --- |
| **Spec** | Caudal, Presión, Vibración, Corriente, Calidad de agua |
| **`FAULT_AFFECTED_VARIABLES`** | `pump_flow_rate`, `pump_vibration`, `pump_pressure`, `pump_current`, `pump_water_quality` |
| **Handler `_apply_cavitation`** | `flow errático (1.5–4.5)`, `pressure errático (0.1–0.6)`, `vibration↑ (+45% sobre crítico)`, `current errático (7.5–10.5)`, `water_quality↑ (+20% sobre crítico)` |
| **Mensaje de alerta** | Caudal, presión, vibración, corriente y calidad de agua |
| **Estado** | ✅ Sincronizado |

#### `overheat` — Sobrecalentamiento

| Capa | Sensores |
| --- | --- |
| **Spec** | Temperatura, Vibración, Corriente, Caudal, Presión |
| **`FAULT_AFFECTED_VARIABLES`** | `pump_temperature`, `pump_vibration`, `pump_current`, `pump_flow_rate`, `pump_pressure` |
| **Handler `_apply_overheat`** | `temperature↑ (+20% sobre crítico)`, `vibration↑ (+15%)`, `current↑ (+5%)`, `flow↓ (degradación 25%)`, `pressure↓ (degradación 25%)` |
| **Mensaje de alerta** | Temperatura, vibración y corriente |
| **Estado** | ✅ Sincronizado |

#### `power_surge` — Sobrecarga eléctrica / Rotor atascado

| Capa | Sensores |
| --- | --- |
| **Spec** | Caudal, Presión, Voltaje, Corriente, Temperatura |
| **`FAULT_AFFECTED_VARIABLES`** | `pump_flow_rate`, `pump_pressure`, `pump_voltage`, `pump_current`, `pump_temperature` |
| **Handler `_apply_power_surge`** | `current↑ (+25% LRA)`, `voltage↓ (~185 V sag)`, `temperature↑ (+15%)`, `flow=0`, `pressure=0` |
| **Mensaje de alerta** | Corriente, voltaje, temperatura, presión y caudal |
| **Estado** | ✅ Sincronizado |

#### `power_outage` — Corte eléctrico

| Capa | Sensores |
| --- | --- |
| **Spec** | Todos (Pasan a 0; Temperatura enfriando progresivamente) |
| **`FAULT_AFFECTED_VARIABLES`** | `pump_voltage`, `pump_current`, `pump_flow_rate`, `pump_pressure`, `pump_vibration`, `pump_temperature` |
| **Handler `_apply_power_outage`** | `voltage=0`, `current=0`, `flow=0`, `pressure=0`, `vibration=0`, `temperature↓ (enfriamiento Newton hacia 22°C)` |
| **Mensaje de alerta** | Voltaje, corriente, caudal, presión, vibración y temperatura |
| **Estado** | ✅ Sincronizado |

#### `bearing_failure` — Falla de rodamientos

| Capa | Sensores |
| --- | --- |
| **Spec** | Vibración, Temperatura, Corriente, Caudal, Presión |
| **`FAULT_AFFECTED_VARIABLES`** | `pump_vibration`, `pump_temperature`, `pump_current`, `pump_flow_rate`, `pump_pressure` |
| **Handler `_apply_bearing_failure`** | `vibration↑ (+35% sobre crítico)`, `temperature↑ (+12%)`, `current↑ (+8%)`, `flow↓ (degradación 25%)`, `pressure↓ (degradación 25%)` |
| **Mensaje de alerta** | Vibración, temperatura y corriente |
| **Estado** | ✅ Sincronizado |

---

### Elevador

#### `motor_stuck` — Motor atascado

| Capa | Sensores |
| --- | --- |
| **Spec** | Temperatura, Velocidad, Corriente, Estado puerta, Voltaje, Vibración |
| **`FAULT_AFFECTED_VARIABLES`** | `elev_temperature`, `elev_speed`, `elev_current`, `elev_door_status`, `elev_voltage`, `elev_vibration` |
| **Targets `_get_fault_telemetry_targets`** | `speed=0`, `current=LRA (85 A)`, `door=closed`, `temperature↑ (+10% sobre crítico)`, `vibration↑ (+15% sobre crítico)`, `voltage=340 V (sag)` |
| **Mensaje de alerta** | Corriente, temperatura, velocidad, vibración, voltaje y estado de puerta |
| **Estado** | ✅ Sincronizado |

#### `door_blocked` — Puerta bloqueada

| Capa | Sensores |
| --- | --- |
| **Spec** | Estado puerta, Velocidad, Corriente |
| **`FAULT_AFFECTED_VARIABLES`** | `elev_door_status`, `elev_speed`, `elev_current` |
| **Targets `_get_fault_telemetry_targets`** | `door=blocked`, `speed=0`, `current=2.5 A (motor de puerta)` |
| **Mensaje de alerta** | Estado de puerta y velocidad |
| **Estado** | ✅ Sincronizado |

#### `overspeed` — Exceso de velocidad

| Capa | Sensores |
| --- | --- |
| **Spec** | Velocidad, Corriente, Estado puerta, Vibración |
| **`FAULT_AFFECTED_VARIABLES`** | `elev_speed`, `elev_current`, `elev_door_status`, `elev_vibration` |
| **Targets `_get_fault_telemetry_targets`** | `speed↑ (+15% sobre crítico)`, `current↑ (alto)`, `door=closed`, `vibration↑ (+10% sobre crítico)` |
| **Mensaje de alerta** | Velocidad, corriente, vibración y estado de puerta |
| **Estado** | ✅ Sincronizado |

#### `overload` — Sobrecarga

| Capa | Sensores |
| --- | --- |
| **Spec** | Carga, Estado puerta, Velocidad, Corriente |
| **`FAULT_AFFECTED_VARIABLES`** | `elev_load`, `elev_door_status`, `elev_speed`, `elev_current` |
| **Targets `_get_fault_telemetry_targets`** | `load↑ (+5% sobre crítico)`, `door=open`, `speed=0`, `current=0` |
| **Mensaje de alerta** | Carga, velocidad, corriente y estado de puerta |
| **Estado** | ✅ Sincronizado |

#### `pos_sensor_fail` — Fallo de sensor de posición

| Capa | Sensores |
| --- | --- |
| **Spec** | Posición, Velocidad, Estado puerta, Corriente |
| **`FAULT_AFFECTED_VARIABLES`** | `elev_position`, `elev_speed`, `elev_door_status`, `elev_current` |
| **Targets `_get_fault_telemetry_targets`** | `position=congelada (stuck_value)`, `speed→0 (tras parada de emergencia)`, `door=closed`, `current→0 (tras parada)` |
| **Mensaje de alerta** | Posición, velocidad y estado de puerta |
| **Estado** | ✅ Sincronizado |

#### `commercial_power_outage` — Corte de energía comercial

| Capa | Sensores |
| --- | --- |
| **Spec** | Voltaje, Corriente, Velocidad, Estado puerta, Temperatura |
| **`FAULT_AFFECTED_VARIABLES`** | `elev_voltage`, `elev_current`, `elev_speed`, `elev_door_status`, `elev_temperature` |
| **Targets `_get_fault_telemetry_targets`** | Fase 1: `voltage=0, current=0, speed→0 (freno), door=closed`. Fase 2 (batería): `voltage=48 V, speed=0.3 m/s (rescate), current=15% nominal`. Fase 3 (completo): `speed=0, door=open, temperature→ambiente` |
| **Mensaje de alerta** | Voltaje, corriente, velocidad, estado de puerta y temperatura |
| **Estado** | ✅ Sincronizado |

#### `traction_loss` — Pérdida de tracción

| Capa | Sensores |
| --- | --- |
| **Spec** | Posición, Velocidad, Corriente, Vibración, Temperatura |
| **`FAULT_AFFECTED_VARIABLES`** | `elev_position`, `elev_speed`, `elev_current`, `elev_vibration`, `elev_temperature` |
| **Targets `_get_fault_telemetry_targets`** | `vibration↑ (+15% sobre crítico)`, `current↓ (20% nominal, marcha en vacío)`, `temperature=ambiente+8°C`, `speed=cruising (motor gira, cabina no se mueve)`. Posición: FSM aplica `pos_change_factor=0.1` (cabina avanza al 10%) |
| **Mensaje de alerta** | Posición, velocidad, corriente, vibración y temperatura |
| **Estado** | ✅ Sincronizado |

---

## 5. Funcionalidades Complementarias

El sistema de fallas se complementa con dos funciones de control industrial:

### Fallas Automáticas (`Toggle Auto Faults`)

Si el usuario activa la "inyección aleatoria de fallas", el motor de simulación calcula intervalos estocásticos mediante distribución de Poisson o temporizadores aleatorios para inyectar fallas de forma autónoma. Esto deshabilita temporalmente los selectores manuales de la interfaz gráfica para garantizar la consistencia de datos.

### Protección Automática (`Toggle Protection`)

Simula el comportamiento de un tablero de control industrial moderno (con guardamotor, relé térmico y variador de frecuencia). Cuando la protección está activa:

1. **Monitoreo de Umbrales:** El sistema evalúa si alguna variable sobrepasa los límites críticos de operación.
2. **Tiempo de Gracia:** Inicia un temporizador (*trip delay*). Si la falla persiste tras vencer el tiempo de gracia, el sistema dispara el relé de disparo (*TRIP*).
3. **Apagado Seguro y Limpieza:** El equipo se apaga (caudal, corriente, velocidad caen a $0$). La falla que originó el disparo se autolimpia (`clear_fault`), permitiendo que el equipo pase al estado de "Listo para Rearme/Reset".

---
