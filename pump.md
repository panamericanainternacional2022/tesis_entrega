# DOCUMENTO 1: SISTEMA DE BOMBA DE AGUA

## 1. Valores Base Ideales (Estado de Reposo)

Antes de presionar "Iniciar", la bomba está apagada, pero el sistema tiene agua y presión estática.

* **Caudal:** 0 L/min
* **Presión:** Presión estática del agua (ejemplo: 1.5 bar, o 0 bar si está al vacío).
* **Temperatura:** Temperatura ambiente (ejemplo: 25 °C).
* **Vibración:** 0 mm/s (o ruido de fondo despreciable, menor a 0.5 mm/s).
* **Nivel del Tanque:** 80% (Tanque lleno o en nivel óptimo).
* **Consumo Eléctrico:** 0 kW
* **Voltaje:** Voltaje nominal de la red (ejemplo: 110 V o 220 V).
* **Corriente:** 0 A

---

## 2. La Física Correcta: Interconexión de Variables

Para que el simulador sea realista y la inyección de fallas funcione de forma matemática, las variables deben depender unas de otras mediante estas reglas lógicas:

### A. La Curva de la Bomba (Presión y Caudal)

La presión ($P$) y el caudal ($Q$) tienen una relación inversa basada en la curva del fabricante. Si el caudal aumenta, la presión cae, y viceversa. Puedes modelarlo con una ecuación simple:

* **Fórmula:** 
$$\text{Presión} = \text{Presion\_Maxima} - (\text{Constante} \times \text{Caudal}^2)$$


* **Inyección de falla "Válvula cerrada":** El caudal cae a 0, por lo tanto, la presión sube a su máximo histórico (Presión de Shut-off).

### B. Consumo Eléctrico, Corriente y Voltaje

La potencia eléctrica activa en un sistema monofásico depende del voltaje ($V$), la corriente ($I$) y el factor de potencia ($F_p$, aproximadamente 0.85 en motores):

* **Fórmula:** 
$$\text{Potencia\_kW} = \frac{\text{Voltaje} \times \text{Corriente} \times F_p}{1000}$$


* **Relación con la carga:** A mayor caudal, la bomba mueve más masa de agua, por lo que el motor hace más esfuerzo. La corriente y los kW aumentan proporcionalmente al caudal. Si el caudal es 0 (válvula cerrada), la corriente cae a su nivel mínimo de operación sin flujo (el motor sigue girando pero sin esfuerzo de empuje).

### C. Temperatura y Vibración

Ambas son variables de pérdida de eficiencia y fricción.

* **Temperatura:** Sube gradualmente estabilizándose según el tiempo de operación. Si el caudal es 0 pero la bomba sigue encendida (bomba trabada o recirculando el mismo líquido), el agua no refrigera el cuerpo de la bomba y la temperatura se dispara exponencialmente.
* **Vibración:** Es directamente proporcional a la velocidad del motor y a la inestabilidad del flujo. Si hay cavitación (baja presión de succión o tanque vacío), la vibración se multiplica por 3 o 4 debido al colapso de las burbujas de aire dentro del impulsor.

### D. Nivel del Tanque

El nivel del tanque disminuye o aumenta en función del tiempo y del caudal actual:

* **Fórmula:** 
$$\text{Nivel\_Actual} = \text{Nivel\_Anterior} \pm (\text{Caudal} \times \Delta t)$$



---

## 3. Tabla de Umbrales y Límites Predeterminados

Valores de referencia planos para una bomba estándar de **220V** con una presión máxima de operación de 4.5 bar y un caudal máximo de 100 L/min:

| Variable | Límite Mínimo | Umbral Bajo (Alerta) | Rango Normal (Estable) | Umbral Alto (Alerta) | Umbral Crítico (Falla) | Límite Máximo |
| --- | --- | --- | --- | --- | --- | --- |
| **Caudal (Q)** | 0 L/min | $< 10$ L/min (Flujo bajo) | 20 a 80 L/min | No aplica | $> 95$ L/min (Tubería rota) | 120 L/min |
| **Presión (P)** | 0 bar | $< 0.8$ bar (Descebado/fuga) | 1.5 a 3.5 bar | $> 4.0$ bar | $> 4.5$ bar (Válvula cerrada) | 6.0 bar |
| **Temperatura** | -10 °C | No aplica | 20 a 60 °C | $> 70$ °C | $> 85$ °C (Sobrecalentamiento) | 120 °C |
| **Vibración** | 0 mm/s | No aplica | 0 a 2.8 mm/s | $> 4.5$ mm/s (Desgaste) | $> 7.1$ mm/s (Cavitación) | 20 mm/s |
| **Nivel del Tanque** | 0% | $< 15\%$ (Riesgo aire) | 20% a 90% | $> 95\%$ | $> 98\%$ (Desborde) | 100% |
| **Voltaje (V)** | 0 V | $< 198$ V | 210 V a 230 V | $> 242$ V | $> 250$ V (Sobretensión) | 300 V |
| **Corriente (I)** | 0 A | $< 2.0$ A (Trabajo en vacío) | 4.0 A a 6.5 A | $> 7.5$ A | $> 9.0$ A (Motor atascado) | 25 A |
| **Consumo Eléctrico** | 0 kW | $< 0.4$ kW | 0.8 kW a 1.4 kW | $> 1.6$ kW | $> 1.9$ kW | 5.0 kW |

---

## 4. Pilares del Bucle de Simulación

Para que el simulador quede perfecto, asegúrate de estructurar el bucle de simulación (*game loop* o *interval*) bajo estos tres pilares:

### 1. El Orden de Ejecución de las Variables (Flujo de Causalidad)

En cada ciclo de tu simulación (por ejemplo, cada 500 ms), el orden en que calculas las variables importa para que la física tenga sentido. Sigue esta cadena de eventos:

```
[Selector de Fallas/Control] ➔ [Voltaje] ➔ [Estado Motor/RPM] ➔ [Caudal] ➔ [Presión] ➔ [Corriente/Consumo] ➔ [Vibración/Temperatura/Tanque]

```

* **El Voltaje manda:** Si el voltaje baja a 0V, la corriente va a 0A y el motor se apaga.
* **El Caudal define la carga:** Primero calculas el caudal ($Q$).
* **La Presión y la Corriente se adaptan al caudal:** Usando las fórmulas anteriores, calculas la presión y los amperios basándote en el caudal actual.

### 2. Programar la Inercia (Transiciones Suaves)

En el mundo real, una bomba tarda unos 2 o 3 segundos en llegar a su velocidad máxima. Debes usar un factor de suavizado o interpolación (*Lerp*) para que las variables "viajen" hacia su valor objetivo.

* **Al encender:** El consumo eléctrico tiene un pico de arranque (la corriente sube hasta 3 veces su valor normal por menos de un segundo) y luego se estabiliza. La vibración sube un instante y baja.
* **Al apagar:** El caudal y la presión no caen a 0 instantáneamente; disminuyen en forma de rampa durante 1 o 2 segundos por la inercia del agua y del motor.

### 3. El Evaluador de Errores (Retraso de Gracia)

Para evitar falsos positivos en tu sistema de detección, el evaluador que compara los valores actuales contra la tabla de umbrales debe ignorar las alertas durante un retraso de gracia (de 3 a 5 segundos) justo después de encender la bomba o al activar/desactivar una falla. Esto permite que la rampa de la inercia (*Lerp*) estabilice las variables en sus nuevos "valores objetivo" antes de que el sistema empiece a arrojar errores en la interfaz.

---

## 5. Lógica de Inyección de Fallas para el Algoritmo

### 1. Sequía (Tanque de Succión Vacío)

El tanque se queda sin agua, por lo que la bomba empieza a succionar aire.

* **Nivel del Tanque:** Cae a 0%.
* **Caudal (Q) y Presión (P):** Caen a 0 de forma inmediata (pérdida de cebado).
* **Corriente (I) y Consumo (kW):** Caen a sus valores mínimos de vacío real (el motor gira libremente sin agua, aprox. 1.5A).
* **Vibración:** Sube ligeramente al inicio por la inestabilidad del aire, luego se normaliza en un valor bajo.

### 2. Descarga Bloqueada (Válvula Cerrada)

Alguien cerró la válvula de salida o la tubería de descarga se tapó por completo.

* **Caudal (Q):** Cae a 0 L/min.
* **Presión (P):** Se dispara al máximo físico (4.5 - 5.0 bar). El agua se comprime contra el bloqueo.
* **Corriente (I) y Consumo (kW):** Bajan a niveles mínimos de operación sin flujo (las bombas centrífugas consumen menos potencia cuando el caudal es cero porque el agua atrapada solo gira con el impulsor).
* **Temperatura:** Sube exponencialmente. Como el agua no fluye, el calor del motor se transfiere al líquido atrapado, arriesgando los sellos mecánicos.

### 3. Ruptura de Tubería (Fuga Crítica)

La tubería de salida se rompe justo después de la bomba, eliminando toda la resistencia al flujo.

* **Caudal (Q):** Se dispara al límite máximo (> 100 L/min) ya que no hay tubería que frene el agua.
* **Presión (P):** Cae casi a 0 bar (toda la energía se convierte en movimiento, no en presión).
* **Corriente (I) y Consumo (kW):** Se disparan a niveles altos / críticos. Al mover tanta masa de agua, el motor trabaja al máximo de su capacidad.

### 4. Cavitación

Ocurre por restricciones en la succión (filtro tapado o succión parcial de aire). Se forman burbujas de vapor que colapsan violentamente dentro de la bomba.

* **Vibración:** Se dispara a nivel Crítico (> 8.0 mm/s). Es el síntoma principal.
* **Presión (P) y Caudal (Q):** Se vuelven altamente inestables. Debes programar que oscilen bruscamente (ej. la presión saltando entre 1.0 y 2.5 bar rápidamente).
* **Corriente (I):** Presenta pequeñas oscilaciones inestables.

### 5. Sobrecalentamiento

Falla en la ventilación del motor o rodamientos desgastados que generan fricción pura.

* **Temperatura:** Sube de forma lineal y constante superando los 85 °C hasta activar el umbral crítico.
* **Vibración:** Sube a niveles de alerta (4.5 - 6.0 mm/s) debido al desgaste mecánico asociado.
* **Las demás variables (Q, P, I):** Se mantienen normales al principio, simulando que la bomba sigue empujando agua mientras se destruye térmicamente.

### 6. Sobrecala Eléctrica (Motor Atascado)

El motor se traba mecánicamente (un objeto atascó el impulsor) o hay un fallo directo en las bobinas.

* **Caudal (Q) y Presión (P):** Caen a 0 (el motor no puede girar).
* **Corriente (I) y Consumo (kW):** Se disparan instantáneamente por encima del límite físico máximo (> 12.0 A). Esto simula la corriente de rotor bloqueado ($I_{LRA}$).
* **Temperatura:** Sube críticamente rápido debido al exceso de corriente.

### 7. Corte Eléctrico

Pérdida total de la fase o energía en la red de alimentación.

* **Voltaje (V):** Cae instantáneamente a 0 V.
* **Corriente (I) y Consumo (kW):** Caen inmediatamente a 0.
* **Caudal (Q), Presión (P) y Vibración:** Caen a 0 siguiendo una rampa de desaceleración suave controlada por la inercia (tardan 1 o 2 segundos en detenerse por completo).

---