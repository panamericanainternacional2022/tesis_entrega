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

## 4. Funcionalidades Complementarias

El sistema de fallas se complementa con dos funciones de control industrial:

### Fallas Automáticas (`Toggle Auto Faults`)

Si el usuario activa la "inyección aleatoria de fallas", el motor de simulación calcula intervalos estocásticos mediante distribución de Poisson o temporizadores aleatorios para inyectar fallas de forma autónoma. Esto deshabilita temporalmente los selectores manuales de la interfaz gráfica para garantizar la consistencia de datos.

### Protección Automática (`Toggle Protection`)

Simula el comportamiento de un tablero de control industrial moderno (con guardamotor, relé térmico y variador de frecuencia). Cuando la protección está activa:

1. **Monitoreo de Umbrales:** El sistema evalúa si alguna variable sobrepasa los límites críticos de operación.
2. **Tiempo de Gracia:** Inicia un temporizador (*trip delay*). Si la falla persiste tras vencer el tiempo de gracia, el sistema dispara el relé de disparo (*TRIP*).
3. **Apagado Seguro y Limpieza:** El equipo se apaga (caudal, corriente, velocidad caen a $0$). La falla que originó el disparo se autolimpia (`clear_fault`), permitiendo que el equipo pase al estado de "Listo para Rearme/Reset".

---