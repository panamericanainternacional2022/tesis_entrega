# Funcionamiento del Sistema de Fallas en el Simulador

Este documento detalla la arquitectura, el flujo y el comportamiento del sistema de fallas implementado en el simulador (Bomba de Agua y Elevador). Explica cómo interactúa la interfaz de usuario con el backend y cómo impactan estas fallas en las variables físicas de los equipos.

---

## 1. Interfaz de Usuario (Frontend)

El selector de fallas se encuentra en la plantilla del panel de control: `monitoring_dashboard.html`. 

### Elementos Principales
- **Selectores HTML**: Existen dos menús desplegables (`<select>`), uno para la bomba (`id="simFaultPump"`) y otro para el elevador (`id="simFaultElevator"`).
- **Controlador JavaScript (`SimulationController`)**: El frontend escucha los cambios en estos selectores mediante el evento `change`. Cuando el usuario selecciona una falla o la opción "Ninguna", se ejecuta el método `_handleFaultChange(device, newFault)`.

### Comunicación con el API
- **Inyectar falla**: Si se selecciona una falla (ej. `dry_run`), se hace una petición `POST` al endpoint `/api/sim/{ID_EDIFICIO}/inject-fault/` con un payload JSON: `{"device": "pump", "fault_type": "dry_run"}`.
- **Limpiar falla**: Si se selecciona "Ninguna", se hace una petición `POST` a `/api/sim/{ID_EDIFICIO}/clear-fault/` con el payload: `{"device": "pump"}`.

Además, existe sincronización en tiempo real mediante *Server-Sent Events (SSE)*. Si una falla se dispara automáticamente o se limpia desde otro cliente, la función `syncFromPayload` del frontend actualiza el selector para reflejar el estado exacto en el backend.

---

## 2. Lógica de Backend (Controladores)

Las llamadas de la API son procesadas en `apps/dashboard/simulation/controls.py`.

- **`sim_inject_fault`**: Llama al núcleo de control del simulador. Primero limpia cualquier falla existente y luego inyecta la nueva. Además, reinicia el temporizador de "gracia de protección" para que el equipo no se apague inmediatamente si la protección está encendida.
- **`sim_clear_fault`**: Limpia la falla solicitada.

### Núcleo de Simulación (`apps/sensors/simulation/controls.py`)
- Al inyectar la falla (`inject_fault`), se guarda el tipo de falla en el estado del simulador (`sim.sim_faults[device] = fault_type`) y se registra el momento exacto (`sim.fault_injected_at`). 
- **Transición**: Se inicia el estado `sim.fault_transition_pump = "injecting"` (o `elev`). Esto le indica al motor de físicas que aplique los efectos de la falla progresivamente (no de golpe).
- Al limpiar la falla (`clear_fault`), se limpia del estado del simulador y se pasa al estado `recovering` (`sim.fault_transition = "recovering"`), lo cual indica al motor que regrese los valores a la normalidad de forma suave, permitiendo que las alertas previas sean marcadas como resueltas en el historial (`History`).

---

## 3. Tipos de Fallas y Variables Afectadas

Cada falla está configurada en `apps/sensors/sensor_config.py` y afecta un subconjunto específico de sensores para imitar un comportamiento real.

### Bomba de Agua
Cada falla inyectada en la bomba altera la simulación física (en `apps/sensors/simulation/physics/pump.py`) de la siguiente manera:

| Falla | Identificador | Comportamiento Físico y Matemático | Sensores afectados |
|---|---|---|---|
| **Sequía (Trabajo en seco)** | `dry_run` | Al no haber fluido, `pump_flow_rate`, `pump_pressure` y el nivel de tanque caen a 0. La falta de fluido para refrigerar el sistema hace que la temperatura (`pump_temperature`) suba un 15% sobre su umbral crítico. El desbalance mecánico eleva la vibración un 25% sobre el crítico. La corriente cae a consumo en vacío (`3.5 A`). | Caudal, Presión, Temperatura, Vibración, Nivel, Corriente |
| **Descarga bloqueada** | `blocked_discharge` | El fluido no puede escapar (`pump_flow_rate` = 0). La energía del motor se convierte en presión extrema (`pump_pressure` sube 25% sobre el crítico - Shut-off head). La temperatura sube un 25% sobre el crítico por estancamiento de líquido en carcasa. La corriente baja a `8.5 A` por la curva P-Q en centrífugas. Nivel de tanque se mantiene estático. | Caudal, Presión, Vibración, Temperatura, Corriente |
| **Ruptura de tubería** | `pipe_burst` | Fuga masiva que dispara el caudal un 30% sobre el crítico (runout), vaciando el tanque a 0%. La presión colapsa a 0. Se eleva la corriente a máxima carga (15% sobre crítico), la vibración un 20% (golpe de ariete), la **temperatura un 15% sobre el crítico por la sobrecarga mecánica del runout** y la turbidez un 25% sobre el crítico por arrastre de sedimentos. | Caudal, Presión, Vibración, Temperatura, Corriente, Calidad de agua, Nivel |
| **Cavitación** | `cavitation` | Formación e implosión de burbujas de vapor. Caudal (1.5-4.5 l/s) y presión (0.1-0.6 bar) altamente oscilantes. Vibración alcanza pico extremo (+45% sobre crítico + jitter). Corriente inestable/baja (7.5-10.5 A) y turbidez alta (+20% sobre crítico por erosión del impulsor). | Caudal, Presión, Vibración, Temperatura, Corriente, Calidad de agua |
| **Sobrecalentamiento** | `overheat` | Ascenso térmico directo. La temperatura supera un 20% el umbral crítico. La corriente es ligeramente alta (+5% sobre crítico) y la vibración sube un 15% por dilatación térmica. **El caudal y la presión presentan una degradación visible del 25%** por pérdida de eficiencia volumétrica del impulsor. | Temperatura, Vibración, Corriente, Caudal, Presión |
| **Sobrecarga eléctrica** | `power_surge` | Sobrecarga por rotor atascado/sobrecorriente. Corriente alcanza pico crítico (+25% sobre crítico, $I > I_{nom}$). El voltaje sufre una caída de tensión (Sag a `185 V`). La temperatura del motor sube un 15% y el sistema cae flujo y presión a 0 por pérdida de RPM/atasco. | Caudal, Presión, Voltaje, Corriente, Temperatura, Vibración |
| **Corte eléctrico** | `power_outage` | Pérdida total de energía. Voltaje, corriente, caudal, presión y vibración caen a 0. Nivel de tanque se congela. La temperatura inicia un enfriamiento progresivo inercial hacia la temperatura ambiente (`22°C`). | Todos (Pasan a 0, Temp enfriando a ambiente) |
| **Falla de rodamientos** | `bearing_failure` | Falla mecánica en el eje. La fricción dispara la vibración a pico extremo (+35% sobre crítico). La temperatura chumacera sube un 12% sobre crítico y la corriente sube un 8% por roce mecánico. Las virutas de metal elevan la turbidez un 20% sobre crítico. **El caudal y la presión presentan una degradación visible del 25%** por pérdida de eficiencia hidráulica y volumétrica del eje dañado. | Vibración, Temperatura, Corriente, Calidad de agua, Caudal, Presión |

### Elevador
Las fallas del elevador se simulan en la máquina de estados y física (en `apps/sensors/simulation/physics/elevator.py`):

| Falla | Identificador | Comportamiento Físico y Matemático | Sensores afectados |
|---|---|---|---|
| **Motor atascado** | `motor_stuck` | El par motor (torque) se vuelve 0.0 (rotor bloqueado). La velocidad cae a 0. Al aplicar energía a un motor inmovilizado, la corriente se dispara un 5% por encima de lo crítico. Esto genera un calentamiento rápido (10% sobre crítico) y vibración severa por el esfuerzo del estator (15% sobre crítico). El voltaje de red sufre una caída (baja al 90% del crítico) debido a la sobrecorriente. | Temperatura, Velocidad, Corriente, Estado puerta, Voltaje, Vibración |
| **Puerta bloqueada** | `door_blocked` | Se fuerza la bandera `_elev_door_obstructed = True`. La máquina de estados impide que el elevador arranque si las puertas no pueden cerrarse. El estado de la puerta se mantiene en `open`, y la velocidad y corriente se quedan en 0 de manera indefinida. | Estado puerta, Velocidad |
| **Exceso de velocidad** | `overspeed` | El gobernador de velocidad y los frenos fallan. La aceleración no se detiene en la velocidad de crucero. La cabina excede la velocidad límite por un 15%, y debido a las fuerzas cinéticas extremas, la vibración supera en un 10% el umbral crítico, al igual que la temperatura de los componentes. | Velocidad, Corriente, Estado puerta, Vibración |
| **Sobrecarga** | `overload` | Se inyecta una masa virtual extra que empuja la lectura de peso un 5% por encima del umbral crítico de bloqueo del edificio. Al detectar que la carga total supera el límite, el sistema de seguridad físico aborta el cierre de puertas (abre puertas), y el motor no puede arrancar (velocidad y corriente a 0). | Carga, Estado puerta, Velocidad, Corriente, Vibración |
| **Fallo de sensor de posición** | `pos_sensor_fail` | La lectura del sensor de posición se congela (se guarda en `_elev_pos_stuck_value`). Un algoritmo del motor detecta una inconsistencia: si el motor se mueve (velocidad > 0) pero la posición no cambia durante más de 1 "tick", se activa el freno de emergencia de inmediato (parada instantánea, velocidad y corriente a 0). | Posición, Velocidad, Estado puerta |
| **Corte de energía comercial** | `commercial_power_outage` | Se corta la alimentación trifásica (voltaje y torque caen a 0). El freno electromecánico actúa por falta de tensión, deteniendo la cabina abruptamente (velocidad cae 2.5 m/s por tick). Tras una pausa, se enciende una batería de rescate de baja potencia que mueve la cabina lentamente (`BATTERY_RESCUE_SPEED`) hasta el piso más cercano para liberar a los pasajeros. | Voltaje, Corriente, Velocidad, Estado puerta, Temperatura |
| **Pérdida de tracción** | `traction_loss` | Los cables patinan sobre la polea. El motor gira a velocidad normal, pero el multiplicador de cambio de posición cae al 10% (la cabina apenas se mueve). Girar en falso con deslizamiento de cables genera golpes mecánicos (vibración 15% sobre crítico). El motor, al girar sin arrastrar la carga completa, consume poca corriente (solo corriente en vacío, 20% de la nominal) pero se sobrecalienta por mala disipación (10% sobre crítico). | Posición, Velocidad, Corriente, Vibración, Temperatura |

---

## 4. Funcionalidades Complementarias

El sistema de fallas se complementa con dos funciones importantes:

### Fallas Automáticas (`Toggle Auto Faults`)
Si el usuario activa la "inyección aleatoria de fallas", el motor (en cada "tick" de simulación) cuenta un tiempo aleatorio y dispara por su cuenta alguna de las fallas mencionadas. Esto desactiva temporalmente los selectores manuales en el frontend para evitar cruces. 

### Protección Automática (`Toggle Protection`)
Cuando la "Protección Automática" está activa (botón con escudo en el UI), el simulador vigila la presencia de fallas. Si una falla crítica persiste por unos segundos (periodo de gracia), el motor **apaga automáticamente el equipo** para prevenir un daño mayor. Al apagar el equipo:
1. Las métricas caen a cero.
2. Si el motor se apaga, la falla se autolimpia (`clear_fault(device)`), lo que devuelve el sistema a un estado seguro, listo para volver a ser encendido.
