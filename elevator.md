# DOCUMENTO 2: SISTEMA DE ELEVADOR ELÉCTRICO

## 1. Valores Base Ideales (Estado de Reposo - En Piso)

Antes de recibir una llamada, el elevador está detenido en un piso con las puertas cerradas y listo para operar.

* **Posición:** Altura exacta del piso actual (ejemplo: 0.0 m en Planta Baja, 3.5 m en Piso 1).
* **Velocidad:** 0.0 m/s.
* **Carga:** Peso actual de los pasajeros (ejemplo: 0 kg si está vacío, o carga nominal base).
* **Conteo de Viajes:** Histórico acumulado (ejemplo: 1245 viajes).
* **Estado de Puerta:** Cerrada (100% segura).
* **Consumo Eléctrico:** Ruido de fondo de la electrónica de control (ejemplo: 0.05 kW).
* **Corriente:** Corriente de mantenimiento / *standby* (ejemplo: 0.5 A).
* **Intentos de Cierre de Puerta:** 0.

---

## 2. La Física Correcta: Interconexión de Variables

Para que el simulador sea realista, las variables dinámicas deben responder de manera lógica y secuencial ante el movimiento y el estado mecánico.

### A. Cinemática y Consumo Eléctrico

La velocidad ($v$), la carga ($m$), y la dirección del viaje determinan el esfuerzo del motor. La potencia eléctrica activa ($P$) depende de la fuerza requerida para vencer la gravedad o acelerar la masa total (considerando el contrapeso, que usualmente balancea la cabina al 40%-50% de la carga máxima):

* **Fórmula de Fuerza neta:**

$$F_{\text{motor}} = (m_{\text{cabina}} + m_{\text{carga}} - m_{\text{contrapeso}}) \cdot g + F_{\text{fricción}} + (m_{\text{total}} \cdot a)$$


* **Fórmula de Potencia:**

$$\text{Potencia\_kW} = \frac{\text{Voltaje} \times \text{Corriente} \times \sqrt{3} \times F_p}{1000}$$


* **Relación con la carga:** A mayor carga en dirección de subida (o cabina vacía en dirección de bajada debido al contrapeso), el motor consume más amperaje. Cuando frena o viaja balanceado, el consumo baja drásticamente o el motor regenera energía.

### B. El Mecanismo de las Puertas e Intentos de Cierre

El estado de la puerta varía de 0% (Totalmente Abierta) a 100% (Totalmente Cerrada y Bloqueada).

* **Lógica de Obstrucción:** Si las puertas intentan cerrar y encuentran resistencia (un objeto o pasajero obstruyendo el sensor o el operador mecánico), el porcentaje de cierre se detiene, la puerta se reabre por completo y la variable `Intentos_Cierre_Puerta` se incrementa en +1.

### C. Posición y Conteo de Viajes

* **Posición:** Se calcula de manera continua integrando la velocidad en el tiempo ($\Delta t$).

$$\text{Posición\_Actual} = \text{Posición\_Anterior} \pm (\text{Velocidad} \times \Delta t)$$


* **Conteo de Viajes:** Se incrementa estrictamente en +1 únicamente cuando la cabina pasa de un estado de "Viaje" (Velocidad > 0) a un estado de "Reposo Exitoso" (Velocidad = 0 y Estado de Puerta = Abierta para desembarcar).

---

## 3. Tabla de Umbrales y Límites Predeterminados

Valores de referencia para un elevador comercial estándar de **380V (Trifásico)**, con capacidad para 800 kg (aprox. 10 personas) y velocidad nominal de 1.5 m/s:

| Variable | Límite Mínimo | Umbral Bajo (Alerta) | Rango Normal (Estable) | Umbral Alto (Alerta) | Umbral Crítico (Falla) | Límite Máximo |
| --- | --- | --- | --- | --- | --- | --- |
| **Posición** | -0.5 m (Foso) | No aplica | 0.0 m a 35.0 m (Pisos) | No aplica | $> 35.5$ m (Sobre-recorrido) | 36.5 m |
| **Velocidad** | 0.0 m/s | No aplica | 0.0 a 1.5 m/s | $> 1.7$ m/s | $> 1.95$ m/s (Acuñamiento) | 2.5 m/s |
| **Carga** | 0 kg | No aplica | 0 a 750 kg | $> 800$ kg | $> 850$ kg (Sobrepeso) | 1200 kg |
| **Consumo Elec.** | 0 kW | No aplica | 0.05 kW a 15.0 kW | $> 18.0$ kW | $> 50.0$ kW (Rotor Bloqueado) | 60.0 kW |
| **Corriente (I)** | 0 A | No aplica | 0.5 A a 28.0 A | $> 32.0$ A | $> 45.0$ A (Rotor Bloqueado) | 80.0 A |
| **Estado Puerta** | 0% (Abierta) | No aplica | Abierta (0%) / Cerrada (100%) | No aplica | 100% (Transición > 6s) | 100% |
| **Intentos Cierre** | 0 | No aplica | 0 a 1 intento | $\ge 2$ intentos | $\ge 3$ intentos (Puerta bloqueada) | 5 |

---

## 4. Pilares del Bucle de Simulación

### 1. El Orden de Ejecución de las Variables (Flujo de Causalidad)

En cada ciclo del simulador (ej. cada 200 ms para alta precisión cinemática), calcula las variables en el siguiente orden estricto:

```
[Entrada de Falla/Llamada] ➔ [Carga] ➔ [Estado Puerta/Intentos] ➔ [Voltaje/Energía] ➔ [Corriente/Consumo] ➔ [Velocidad Motor] ➔ [Posición Sensor] ➔ [Conteo de Viajes]

```

* **Las puertas comandan el viaje:** Si el `Estado Puerta` no es igual a 100%, la `Velocidad` se fuerza a 0 m/s de inmediato por seguridad.
* **La Carga define la potencia:** Primero se evalúa el peso para calcular la fuerza que el motor debe realizar antes de modificar la corriente.

### 2. Programar la Inercia (Transiciones Suaves)

Un elevador requiere curvas de aceleración y desaceleración suaves (*S-Curve*) para el confort de los pasajeros.

* **Perfil de Velocidad:** Usa una rampa de aceleración de unos 1.5 a 2.0 segundos para pasar de 0 a 1.5 m/s.
* **Corriente de Arranque:** Al romper la inercia, la corriente y el consumo eléctrico deben experimentar un pico momentáneo de hasta 2.5 veces el valor nominal durante 400 ms, estabilizándose luego según la carga del viaje.

### 3. El Evaluador de Errores (Retraso de Gracia)

El sistema de seguridad debe ignorar los picos transitorios de corriente durante los primeros 600 ms del arranque del motor. Asimismo, debe otorgar un margen de tiempo en la detección de fallos de posición mientras la cabina realiza la nivelación fina en el piso.

---

## 5. Lógica de Inyección de Fallas para el Algoritmo

### 1. Motor Atascado (Falla Mecánica / Bloqueo de Tracción)

Un freno mecánico que no abre o una deformación en las guías impide que la cabina se mueva a pesar de recibir energía.

* **Velocidad:** Cae a 0 m/s instantáneamente (o no sube a pesar de la orden de marcha).
* **Corriente (I) y Consumo (kW):** Se disparan críticamente al límite máximo de rotor bloqueado ($> 45\text{ A}$ / $> 50\text{ kW}$).
* **Estado de Puerta:** Permanecen en 100% (Cerradas).
* **Posición:** Estática (no varía).

### 2. Puerta Bloqueada (Obstrucción Persistente)

Un objeto interrumpe el paso de las puertas de la cabina o del piso repetidamente.

* **Intentos de Cierre de Puertas:** Incrementa progresivamente en cada ciclo fallido (1, 2, 3...). Al llegar a 3, se dispara la condición crítica.
* **Estado de Puerta:** Oscila continuamente (por ejemplo: varía de 0% a 40%, detecta obstrucción, regresa a 0%).
* **Velocidad:** Se mantiene estrictamente en 0 m/s (Bucle de viaje bloqueado).
* **Consumo Eléctrico:** Pequeños picos intermitentes cada vez que el operador de la puerta intenta forzar el cierre.

### 3. Exceso de Velocidad (Falla de Control de Tracción / Caída Libre Simulada)

El variador de frecuencia falla o el cable patina perdiendo el control del descenso.

* **Velocidad:** Supera la velocidad nominal superando los 1.95 m/s de forma lineal o abrupta.
* **Posición:** Cambia a un ritmo mucho más rápido de lo diseñado en el plano físico.
* **Consumo Eléctrico y Corriente:** Caen a valores mínimos o erráticos (el motor ya no ejerce control de retención).

### 4. Sobrecarga

Demasiados pasajeros ingresan a la cabina superando el límite de diseño.

* **Carga:** Se establece un valor estático por encima del umbral crítico ($> 850\text{ kg}$).
* **Estado de Puerta:** El sistema impide físicamente el cierre; las puertas se abren por completo (0%) y permanecen bloqueadas en ese estado.
* **Velocidad:** Permanecerá en 0 m/s. Se inhabilita el arranque del motor.

### 5. Fallo del Sensor de Posición (Desorientación de Cabina)

El encoder del motor o los sensores magnéticos de los pisos dejan de enviar datos o envían datos corruptos.

* **Posición:** Se congela en un valor estático o se va a NaN / 0 de golpe, mientras el elevador sigue en movimiento físico real.
* **Velocidad:** Sigue marcando un valor de viaje (ej. 1.5 m/s).
* **Consecuencia del Algoritmo:** El tiempo de viaje excede el estimado para cambiar de piso, activando la parada de emergencia por tiempo de carrera límite superado (*Run Timer*).

### 6. Corte de Energía Comercial

Pérdida total del suministro eléctrico del edificio.

* **Voltaje / Señal de Red:** Cae a 0 V de forma abrupta.
* **Consumo y Corriente:** Caen inmediatamente a 0.
* **Velocidad y Puertas:** La velocidad desacelera a 0 m/s violentamente por la acción instantánea de los frenos mecánicos de emergencia (caída por inercia menor a 0.5 segundos). Las puertas quedan bloqueadas en su último estado porcentual.

---

## 6. Estructura de Control para Programación (Seudocódigo)

### Paso 1 (Definir Objetivos de Falla)

```text
Si Falla == "MOTOR_ATASCADO":
    Velocidad_Objetivo = 0
    Corriente_Objetivo = Corriente_Rotor_Bloqueado (45 A)
    Consumo_Objetivo = Consumo_Maximo (50 kW)
    Posicion_Objetivo = Posicion_Actual  // No cambia

Si Falla == "PUERTA_BLOQUEADA":
    Velocidad_Objetivo = 0
    Si Estado_Puerta_Actual > 40:
        Intentos_Cierre_Puerta = Intentos_Cierre_Puerta + 1
        Estado_Puerta_Objetivo = 0 // Reabrir inmediatamente

```

### Paso 2 (Aplicar Transición Cinemática en cada ciclo)

```text
Velocidad_Actual = Velocidad_Actual + ((Velocidad_Objetivo - Velocidad_Actual) * Factor_Aceleracion)
Corriente_Actual = Corriente_Actual + ((Corriente_Objetivo - Corriente_Actual) * Factor_Inercia_Electrica)

```

---

## 7. Arquitectura del Sistema de Alertas y Recomendaciones

El motor de reglas de seguridad evalúa el estado del elevador empleando un análisis jerárquico para mitigar falsas alarmas y proveer soluciones seguras.

### A. Capa 1: Alertas de Umbral (Por Componente)

Monitorea los sensores individuales de manera aislada contra los parámetros de la tabla.

* **Ejemplo:** Si `Carga > 850 kg`, emite una alerta independiente de *Exceso de Peso en Cabina*, activando la señal audible de cabina.

### B. Capa 2: Motor de Diagnóstico (Causa Raíz)

Consolida múltiples eventos en un diagnóstico único de operación para el personal de mantenimiento.

* **Ejemplo:** Si la corriente sube a 46 A, la velocidad es 0 m/s y la orden de viaje está activa, la Capa 2 cancela las alertas genéricas de consumo alto y emite un fallo único de **Motor Atascado**.

---

## 8. Formato de Despliegue en la Interfaz (UI/UX)

### 1. Bloque Crítico: Diagnóstico y Recomendación (Causa Raíz)

> **[FALLO CRÍTICO] Mecanismo de Puerta Bloqueado**
> * **Recomendación:** Se han registrado 3 intentos fallidos consecutivos de cierre de puertas en el Piso 4. La cabina ha quedado bloqueada por seguridad. Inspeccione visualmente el riel de la puerta mecánica en busca de escombros u objetos atrapados en la pisadera del piso. Activate la apertura manual desde la central si hay pasajeros a bordo.
> 
> 

### 2. Bloque Técnico: Evidencia de Sensores (Telemetría Soportada)

* **[Estado Puerta]:** 42% ➔ *Falla en completar el ciclo de cierre*
* **[Intentos Cierre]:** 3 ➔ *Umbral Crítico Superado*
* **[Velocidad]:** 0.0 m/s ➔ *Bloqueo de seguridad de marcha activo*
* **[Consumo Eléctrico]:** 1.2 kW ➔ *Picos cíclicos debido a reintentos del operador*