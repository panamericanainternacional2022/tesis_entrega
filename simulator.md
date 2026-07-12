# ESPECIFICACIONES TÉCNICAS DEFINITIVAS DEL SIMULADOR

Este documento constituye la única fuente de verdad (*Single Source of Truth*) para los límites, umbrales, estados iniciales y comportamiento físico ante fallas del simulador.

---

## 1. DICCIONARIO DE SENSORES Y UNIDADES

### Sistema de la Bomba

* **Caudal (`pump_flow_rate`):** `l/s`
* **Presión (`pump_pressure`):** `bar`
* **Temperatura (`pump_temperature`):** `°C`
* **Vibración (`pump_vibration`):** `mm/s`
* **Nivel de tanque (`pump_tank_level`):** `%`
* **Voltaje (`pump_voltage`):** `V` (Monofásico comercial)
* **Corriente (`pump_current`):** `A`
* **Calidad de agua (`pump_water_quality`):** `ppm`

### Sistema del Elevador

* **Posición (`elev_position`):** `piso` (Rango discreto: 0.0 a 5.0)
* **Velocidad (`elev_speed`):** `m/s`
* **Carga (`elev_load`):** `kg`
* **Estado de puerta (`elev_door_status`):** *Sin unidad* (0.0 = Cerrada, 1.0 = Abierta)
* **Temperatura (`elev_temperature`):** `°C`
* **Vibración (`elev_vibration`):** `mm/s`
* **Voltaje (`elev_voltage`):** `V` (Trifásico industrial)
* **Corriente (`elev_current`):** `A`

---

## 2. MATRIZ DE CONTROL: ESTADOS INICIALES, LÍMITES Y UMBRALES

### Sistema: BOMBA

* **Arranque Seguro (Time Step 0):** `flow=0.0`, `pressure=1.0`, `temp=25.0`, `vibration=0.0`, `tank=50.0`, `voltage=220.0`, `current=0.0`, `water_quality=150.0`.
* **Control de bomba:** La bomba se controla únicamente de forma manual. No existe float switch automático por nivel de tanque.

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

* **Arranque Seguro (Time Step 0):** `position=0.0`, `speed=0.0`, `load=0.0`, `door_status=0.0`, `temp=25.0`, `vibration=0.0`, `voltage=380.0`, `current=0.0`.

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

---

## 3. COMPORTAMIENTO DINÁMICO EN LÍNEA BASE (SIN FALLAS)

* **Bomba Activa:** Caudal `~12.0–16.0 l/s`, presión `~3.5 bar`, corriente `~13.0 A`. La temperatura asciende paulatinamente hasta estabilizarse en `~45.0 °C`. Vibración residual de `~1.5 mm/s`.
* **Bomba Apagada:** Todos los valores operativos caen a 0. Temperatura converge a `22.0 °C` (temperatura ambiente). Voltaje se mantiene en `~220 V` (red disponible).
* **Elevador Activo:** Pico transitorio de corriente al arrancar, estabilizándose en `~12.0–18.0 A` en régimen crucero (`1.0 m/s`). Temperatura del motor `~40–50 °C`. Cambios de posición continuos y lineales.

---

## 4. MATRIZ DE INYECCIÓN DE FALLAS (COMPORTAMIENTO EN CADENA)

**NOTA IMPORTANTE SOBRE FÍSICAS DE FALLA:** Al inyectarse una falla, los sensores saltan de **forma directa e instantánea** a los valores anómalos o críticos correspondientes, sin pasar por rampas progresivas. Esto está diseñado así para facilitar pruebas y validación inmediata del sistema de alertas en el entorno de desarrollo y pruebas.

### Inyecciones en Bomba

1. **Sequía (Dry Run):**
* `tank_level` ➔ 0%
* `flow_rate` ➔ 0.0
* `pressure` ➔ 0.0
* `current` ➔ Cae drásticamente
* `temperature` ➔ Sube por falta de refrigeración fluida.


2. **Descarga Bloqueada:**
* `flow_rate` ➔ 0.0
* `pressure` ➔ Dispara a Máximo/Crítico
* `current` ➔ Sube levemente
* `temperature` ➔ Sube rápido por fricción hidrodinámica interna.


3. **Ruptura de Tubería:**
* `flow_rate` ➔ Sube a picos máximos
* `pressure` ➔ Cae a ~0.0
* `tank_level` ➔ Se vacía de forma acelarada.


4. **Cavitación:**
* `vibration` ➔ Dispara a Crítico
* `pressure` y `flow_rate` ➔ Oscilaciones violentas e inestables.


5. **Sobrecalentamiento:**
* `temperature` ➔ Salta directamente a Límite Físico (100.0 °C).

6. **Sobrecarga Eléctrica:**
* `current` ➔ Salta directo a valor Crítico (30.0 A).
* `voltage` ➔ Sube a valor anómalo (300.0 V).
* `temperature` ➔ Sube de inmediato por Efecto Joule (90.0 °C).


7. **Corte Eléctrico:**
* `voltage` ➔ 0.0
* `current` ➔ 0.0
* `flow_rate` y `pressure` ➔ 0.0 de forma inmediata.


8. **Falla de Rodamientos:**
* `vibration` ➔ Salta directo a Crítico (10.0 mm/s)
* `temperature` motor ➔ Salta a Crítico (90.0 °C)
* `current` ➔ Incremento por fricción parásita (25.0 A)
* `water_quality` ➔ Sube por contaminación (600.0 ppm)



### Inyecciones en Elevador

1. **Motor Atascado:**
* `current` ➔ Dispara a Límite Máximo (Rotor bloqueado)
* `speed` ➔ 0.0
* `temperature` ➔ Sube exponencialmente.


2. **Puerta Bloqueada:**
* `door_status` ➔ Abierta (1.0)
* *Intervención:* `speed` ➔ 0.0 y `current` ➔ 0.0 (El sistema aborta el arranque).


3. **Exceso de Velocidad:**
* `speed` ➔ Supera umbral Crítico de inmediato (>1.6 m/s, ej. 2.0 m/s)
* `vibration` ➔ Incrementa a Crítico (6.5 mm/s) por descontrol cinético.


4. **Sobrecarga:**
* `load` ➔ >800.0 kg
* *Intervención:* El sistema bloquea físicamente el motor (`speed = 0.0`, `current = 0.0`).


5. **Fallo de Sensor de Posición:**
* `position` ➔ Entrega `NaN` o valores erráticos. Debe gatillar parada de emergencia inmediata (tiempo de respuesta ≤ 1 tick).


6. **Corte de Energía Comercial:**
* `voltage` ➔ 0.0
* `current` ➔ 0.0
* `speed` ➔ 0.0 inmediato por actuación de frenos mecánicos de seguridad (caída por falta de energía).


7. **Pérdida de Tracción:**
* `speed` (motor) ➔ Normal o alta
* `position` ➔ No varía o cambia muy lento (desfase físico)
* `current` ➔ Baja significativamente (la polea patina libre de carga).