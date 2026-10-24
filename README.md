# Avance de Proyecto 2: Control Multimodal del Cursor (Vista + Manos) — Visión Artificial

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![MediaPipe Face & Hands](https://img.shields.io/badge/MediaPipe-Face%20%2B%20Hands-brightgreen.svg)](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.x-red.svg)](https://opencv.org/)
[![Tests](https://img.shields.io/badge/Tests-74%20passing-success.svg)](https://github.com/Panazolito/PF_VA)

Proyecto semestral de **Tópicos Especiales I (Visión Artificial)** — **Universidad Tecnológica de Panamá (UTP)**, 2do Semestre 2026.

Sistema multimodal sin contacto que combina **seguimiento ocular de iris (Vista)** para desplazar el cursor sin fatiga de brazo (*Gorilla Arm*) y **gestos manuales relajados (Manos)** para ejecutar clics, arrastre y scroll, integrando un **módulo de aislamiento de usuario activo (User Lock)** para operar de forma segura en entornos multi-persona.

---

## Autores

- **Victor Sánchez** — 20-70-7342
- **Crisarys Vasquez** — 8-1003-2328
- **Juan Gonzalez** — 8-996-1703
- **Alexandra Esteves** — 20-70-7349

---

## Sistema de Seguridad Multi-Persona (User Lock)

En entornos del mundo real como **quirófanos**, **plantas industriales** o **salones de clase**, es habitual que varias personas se muevan dentro del campo visual de la cámara. Un sistema convencional con `max_num_hands=1` elige manos de forma arbitraria, saltando de una persona a otra, o puede provocar clics no intencionados que representan riesgos graves.

Para prevenir esta limitación, el sistema implementa una **arquitectura de 3 capas combinadas**:

```mermaid
stateDiagram-v2
    [*] --> INACTIVO : Inicio seguro (cursor bloqueado)

    INACTIVO --> ACTIVANDO : Palma abierta sostenida (dedos [1,1,1,1,1])
    ACTIVANDO --> ACTIVO : Confirmación sostenida (>= 2.0s)
    ACTIVANDO --> INACTIVO : Interrupción o mano retirada

    ACTIVO --> ACTIVO : Rastreo por continuidad espacial (centroide <= 150px)
    ACTIVO --> PERDIDO : Mano desaparece del encuadre
    ACTIVO --> PAUSADO : Gesto de pausa (puño cerrado >= 2.0s)

    PERDIDO --> ACTIVO : Reaparición dentro del umbral (< 3.0s)
    PERDIDO --> INACTIVO : Timeout de ausencia (>= 3.0s sin reaparición)

    PAUSADO --> ACTIVO : Reactivación (palma abierta >= 1.0s)
    PAUSADO --> INACTIVO : Timeout en pausa (>= 10.0s sin actividad)
```

### Capas de Protección

1. **Gesto de Activación con Selección por Proximidad:**
   - Inicia **inactivo por defecto**. Ninguna acción del mouse se dispara accidentalmente.
   - Si varias personas están frente a la cámara, se evalúa el área de la mano (la más grande = persona más cercana).
   - Se requiere sostener la palma abierta durante **2.0 segundos** para tomar el control, con barra de progreso visual en el HUD.

2. **Bloqueo por Continuidad Espacial:**
   - Tras la activación, el sistema memoriza el centroide espacial de la mano activa.
   - En cada cuadro compara las manos detectadas (`max_num_hands=2`) y selecciona exclusivamente la más cercana al último centroide dentro del umbral de 150 px.
   - Manos secundarias de asistentes, estudiantes o transeúntes son **ignoradas activamente** y mostradas como atenuadas.

3. **Tolerancia a Oclusiones, Pausa Rápida y Timeout:**
   - **Pausa de seguridad:** El operador puede sostener el puño cerrado 2 segundos para pausar el sistema y congelar el cursor (ideal para gesticular o manipular instrumental).
   - **Tolerancia temporal (3s):** Si la mano sale momentáneamente del encuadre, el sistema espera 3 segundos antes de liberar el control.
   - **Liberación automática:** Tras el timeout, regresa al estado `INACTIVO` de forma segura.

### Por qué esta solución es ideal para Quirófanos
- **Inactividad por defecto:** Cero clics accidentales mientras el cirujano no haya tomado el control explícitamente.
- **Rastreo gestual sobre rastreo facial:** En quirófano, las mascarillas quirúrgicas, gorros y gafas impiden un reconocimiento facial fiable. Los gestos manuales con bloqueo cinemático son la solución óptima.
- **Congelamiento instantáneo:** El gesto de pausa permite interactuar con instrumentos sin riesgo de mover la interfaz.

---

## Tabla de Gestos y Comandos (Modo Híbrido Vista + Manos)

### Control de Sesión y Ergonomía (Anti-Fatiga *Gorilla Arm*)

| Gesto / Acción | Dedos / Estado | Duración | Acción |
|-------|-------|----------|--------|
| Palma abierta | `[1, 1, 1, 1, 1]` | 2.0 s | **Activar control** (bloquear usuario activo) |
| Bajar la mano al escritorio | Rostro presente | Libre | **Descanso de brazo** (la vista sigue moviendo el cursor sin perder la sesión) |
| Apoyar/asomar mano bloqueada | Misma mano | Inmediato | **Reanudar gestos** desde posición baja de descanso sin reactivar 2 s |
| Puño cerrado | `[0, 0, 0, 0, 0]` | 2.0 s | **Pausar control** (congelar cursor) |
| Palma abierta (en pausa) | `[1, 1, 1, 1, 1]` | 1.0 s | **Reactivar control** desde pausa |
| Ausencia total (sin rostro ni mano) | - | 3.0 s | **Liberación automática** (retorno a INACTIVO) |

### Acciones del Cursor (Una vez ACTIVO)

| Entrada / Gesto | Visual | Acción en el Sistema Operativo |
|-------|--------|--------------------------------|
| Mirada (Iris 468 / 473) | 👁️ Face Mesh | **Mover cursor** con Filtro One Euro y congelado automático en parpadeo |
| Acercar pulgar e índice (postura relajada) | Distancia norm < 0.52 | **Pre-pellizco / Congelar mirada** (Click Lock: cero desviación) |
| Pellizco pulgar + índice (relajado u OK) | Distancia norm < 0.32 | **Clic izquierdo** (no exige mantener el índice rígido `[0,1,0,0,0]`) |
| Pellizco + Desplazar mano / mirar | Movimiento > 15px | **Arrastre (Drag & Drop)** hacia donde apunta la vista |
| Pellizco pulgar + medio (relajado) | Pulgar + Medio | **Clic derecho** contextual (con posición congelada) |
| Índice + medio quietos + Mirada | `[0, 1, 1, 0, 0]` | **Scroll con la Vista** ( gesto de victoria quieto como pedal y mira arriba/abajo para deslizar sin rebote) |
| Teclas `+` / `s` y `-` / `a` | Teclado | **Aumentar / Reducir sensibilidad ocular** en vivo |
| Tecla `r` | Teclado | **Recalibrar umbral basal de parpadeo** |
| Presionar `q` o `Esc` | Teclado | **Salir del programa** de forma segura |

---

### 1. Punto de Anclaje Estable en el Nudillo del Índice (Landmark 5: `INDEX_FINGER_MCP`)
- **Problema:** En sistemas tradicionales se rastrea la punta del índice (Landmark 8). Cuando el usuario flexiona las falanges para tocar el pulgar, la punta cae y se desplaza inevitablemente.
- **Solución:** Se desacopla el puntero del extremo del dedo. El cursor es guiado por la articulación metacarpofalángica del índice (Landmark 5), que pertenece a la estructura rígida de la palma. Mientras la punta del dedo se flexiona libremente para cliquear, el nudillo permanece estable en el espacio tridimensional.

### 2. Filtro Adaptativo One Euro (*1 € Filter*)
- **Referencia Científica:** G. Casiez, N. Roussel y D. Vogel, *"1 € Filter: A Simple Speed-based Low-pass Filter for Noisy Input in Interactive Systems,"* Proc. ACM CHI, 2012.
- **Formulación Matemática:**
  $$\alpha(T_e, f_c) = \frac{1}{1 + \frac{1}{2\pi f_c T_e}}$$
  $$f_c = f_{c_{\min}} + \beta \cdot |\hat{\dot{x}}_i|$$
- **Comportamiento:**
  - En reposo ($\dot{x} \approx 0$): La frecuencia de corte desciende a $f_{c_{\min}} = 1.0\text{ Hz}$, filtrando el temblor biológico y el ruido sensor de la cámara con máxima atenuación.
  - En movimiento rápido: La derivada de velocidad incrementa dinámicamente $f_c$ mediante el coeficiente $\beta = 0.007$, anulando el rezago (*lag*) y permitiendo trazos instantáneos.
  - Con **zona muerta anti-temblor** (`deadzone_px = 3`), el reposo es matemáticamente estático (0.0 px de desviación).

### 3. Histéresis Dual con Distancia Normalizada y Confirmación Temporal
- **Invarianza a la Distancia de la Cámara:** Se calcula el tamaño anatómico de la palma como la distancia euclidiana entre la muñeca (Landmark 0) y el nudillo medio (Landmark 9), una referencia osteológica invariable a la flexión de dedos:
  $$d_{\text{norm}} = \frac{\text{distancia}(\text{Pulgar}_{\text{tip}}, \text{Índice}_{\text{tip}})}{\text{distancia}(\text{Muñeca}, \text{Medio}_{\text{MCP}})}$$
  Esto asegura idéntica sensibilidad de clic ya sea que el usuario se ubique a 40 cm o a 2 metros de la cámara.
- **Histéresis Dual ($T_{\text{ON}} = 0.32$, $T_{\text{OFF}} = 0.45$):** Para activar el clic se requiere cerrar a $d < 0.32$. Para liberarlo se requiere abrir a $d > 0.45$. La banda intermedia absorbe las micro-vibraciones de la mano sin provocar desconexiones intermitentes (*chattering*).
- **Confirmación Temporal:** Requiere $N = 2$ cuadros consecutivos para transicionar, descartando anomalías o saltos espurios de un solo cuadro.

### 4. Congelado de Cursor (*Pre-Pinch Lock*) y Zona Muerta de Arrastre (*Drag Deadzone*)
- **Congelado de Intención ($T_{\text{PRE}} = 0.52$):** Tan pronto como los dedos inician el movimiento de cierre, el cursor se congela instantáneamente en la coordenada del blanco (`[FIJADO]`).
- **Absorción de Rebote Post-Clic (200 ms):** Al separar los dedos tras un clic, el cursor permanece congelado 200 ms adicionales para absorber la oscilación de rebote elástico.
- **Zona Muerta de Arrastre (15 px):** Mientras los dedos permanecen en pellizco:
  - Si el desplazamiento de la mano es $\le 15\text{ px}$, se interpreta como un clic estático limpio (`pyautogui.click()`).
  - Si el usuario desplaza la mano intencionalmente $> 15\text{ px}$, el cursor se desbloquea y conmuta dinámicamente a **arrastre activo** (`pyautogui.mouseDown()`), finalizando al soltar con `pyautogui.mouseUp()`.

---

## 🛠️ Requisitos del Sistema

- **Python:** 3.10 o superior (validado en Python 3.12)
- **Cámara:** Webcam convencional (720p / 1080p a 30 FPS recomendada)
- **Sistema Operativo:** Windows 10 / 11 (compatible con eventos de PyAutoGUI)

### Dependencias

```txt
opencv-python
mediapipe
pyautogui
numpy
```

---

## Instalación y Ejecución

```bash
# 1. Clonar el repositorio
git clone https://github.com/Panazolito/PF_VA.git
cd PF_VA

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar el sistema
python main.py
```

## 📄 Licencia y Contexto Académico

Proyecto desarrollado para el curso **Tópicos Especiales I (Visión Artificial)** — **Universidad Tecnológica de Panamá (UTP)**.
Autores: Victor Sánchez, Crisarys Vasquez, Juan Gonzalez, Alexandra Esteves.
