# Formato de Propuesta de Proyecto

**Visión Artificial - Propuesta de Proyecto**

**Universidad Tecnológica de Panamá**
Facultad de Ingeniería de Sistemas Computacionales
Grupo 1IL143

## Autores del Proyecto

(Nombre completo / Cédula del autor)

- Victor Sánchez - 20-70-7342
- Crisarys Vasquez - 8-1003-2328
- Juan Gonzalez - 8-996-1703
- Alexandra Esteves - 20-70-7349

## Título Tentativo

Desarrollo de un Sistema Multimodal de Control de Interfaz de Usuario mediante Rastreo de Mirada y Gestos Manuales en Tiempo Real

## Objetivo General

Desarrollar un sistema de software multimodal en Python mediante algoritmos de Visión Artificial sobre video en tiempo real que permita el control del cursor y periféricos del sistema operativo mediante dos modos de interacción seleccionables: rastreo ocular/facial y reconocimiento de gestos manuales estilo Hand-Tracking.

## Objetivos Específicos

- Extraer y rastrear los puntos clave del rostro e iris para la estimación de mirada, e implementar el modelo de puntos clave de la mano para la detección de gestos espaciales.
- Diseñar un modo de interacción manual enfocado en gestos intuitivos (como la unión del dedo índice y pulgar) para simular los eventos de clic y arrastre del mouse.
- Desarrollar algoritmos de calibración e interpolación espacial para mapear tanto el rango de movimiento ocular como la posición de las manos a la resolución del monitor.
- Aplicar técnicas de filtrado espacial y temporal (el llamado Filtro One Euro) para mitigar el temblor involuntario y estabilizar la trayectoria del cursor en ambos modos.
- Evaluar el rendimiento del sistema en términos de latencia, cuadros por segundo y precisión de selección en la interfaz de usuario para ambos modos de operación.

## Descripción Resumida de la Propuesta

Las interfaces tradicionales dependen de periféricos físicos, lo que limita la accesibilidad. Este proyecto consiste en un sistema de control de interfaz de usuario en tiempo real mediante una cámara web convencional, con un enfoque multimodal. El sistema cuenta con dos modos operacionales:

- **Modo Ocular/Facial:** captura las coordenadas del iris mediante MediaPipe Iris para mapear el movimiento de los ojos al cursor y ejecuta clics mediante parpadeos calculados por Eye Aspect Ratio.
- **Modo Gestual (Hand-Tracking):** detecta los puntos clave de la mano permitiendo controlar el cursor con el dedo índice y ejecutar clics o arrastres uniendo el pulgar y el índice, emulando la interacción de visores como Meta Quest.

En ambos modos se aplica el filtro One Euro para eliminar el temblor y estabilizar la señal. Toda la arquitectura se desarrollará en Python utilizando OpenCV para el procesamiento de imágenes y la librería PyAutoGUI para enviar los eventos de control directamente al sistema operativo.

## Justificación de la Propuesta

La necesidad de realizar este proyecto radica en la creación de soluciones de interacción Hombre-Máquina (HCI) flexibles, accesibles y de bajo costo. Las tecnologías comerciales de seguimiento ocular o sensores espaciales dedicados son sumamente costosas o requieren hardware propietario especializado.

Desarrollar este sistema multimodal demuestra que es posible llevar esquemas de interacción modernos (como el Hand-Tracking de visores de realidad aumentada y el rastreo de mirada) a computadoras convencionales mediante procesamiento de video estándar. De no realizarse el proyecto, se pierde la oportunidad de crear herramientas de software incluyentes adaptables a distintas necesidades motoras y se desaprovecha el potencial de la Visión Artificial para transformar la ergonomía y usabilidad en estaciones de trabajo y entornos sanitarios.

## Mitigación de Limitaciones en Entornos Reales Multi-Persona y Consideraciones de Seguridad

Uno de los desafíos más críticos identificados para el despliegue práctico del sistema en entornos reales (como quirófanos hospitalarios, plantas industriales, salones de clase o salas de conferencias) es la presencia simultánea de múltiples personas frente a la cámara. Un algoritmo convencional de visión artificial configurado con detección unitaria (`max_num_hands=1` o `max_num_faces=1`) selecciona un usuario de manera arbitraria y no determinista, alternando entre personas o permitiendo que transeúntes tomen el control accidentalmente.

### Evaluación de Estrategias de Aislamiento

| Estrategia | Principio de Operación | Limitación / Riesgo |
|------------|------------------------|---------------------|
| **Limitar detección** | Forzar `num_faces=1` y `num_hands=1` | Selección arbitraria; si otra persona se mueve más rápido o está mejor iluminada, roba el control. |
| **Usuario más cercano** | Elegir la mano o rostro con mayor área de bounding box | Cualquier persona que pase temporalmente por delante se apodera de la interfaz. |
| **Zona de interacción (ROI)** | Procesar únicamente una región geométrica fija | Restringe drásticamente la libertad de movimiento y la ergonomía del operador. |
| **Gesto de activación** | Requiere una postura específica (ej. palma abierta sostenida 2 s) | Por sí sola no resuelve qué ocurre si otra persona interviene después de activar. |
| **Bloqueo de usuario (User Lock)** | Seguir al usuario activo por continuidad espacial ignorando al resto | Requiere una política robusta para manejar oclusiones temporales y reconexión. |

### Arquitectura de Seguridad Implementada

Para resolver esta limitación de manera integral, el proyecto incorpora un módulo especializado de aislamiento (`user_lock.py`) basado en una **arquitectura híbrida de tres capas**:

1. **Gesto de Activación con Priorización por Proximidad:** El sistema inicia en estado inactivo por defecto para evitar clics accidentales. Si hay varias manos en el encuadre, evalúa el área del bounding box (la más cercana) y exige mantener la palma abierta durante 2 segundos continuos con retroalimentación visual progresiva en pantalla.
2. **Bloqueo por Continuidad Espacial:** Se procesan múltiples manos (`max_num_hands=2`), pero el control se bloquea exclusivamente sobre el centroide cinemático de los 21 landmarks de la mano del usuario activo. Toda mano externa que ingrese al encuadre es clasificada como intruso y descartada de las acciones del sistema operativo.
3. **Pausa Rápida y Liberación por Timeout:** El operador puede congelar el cursor inmediatamente mediante un gesto de pausa (puño cerrado sostenido 2 s) para manipular instrumental u objetos físicos sin riesgo. Si el usuario retira la mano del encuadre, el sistema tolera oclusiones breves (3 s) y posteriormente libera el control de forma automática volviendo al estado inactivo.

### Mitigación del Error Biomecánico y Estabilización de Clics (Anti-Drift)

En el diseño de interfaces táctiles sin contacto (touchless HCI), uno de los problemas de usabilidad más documentados es el **desplazamiento involuntario o click drift**: al juntar el pulgar y el índice para cliquear, el acoplamiento biomecánico de las falanges arrastra la punta del dedo entre 15 y 45 píxeles en el encuadre. En aplicaciones de precisión (como software quirúrgico o dibujo técnico), esto causa un alto porcentaje de clics fallidos fuera del objetivo.

Para eliminar este fenómeno sin comprometer la fluidez de interacción, el sistema implementa una arquitectura de estabilización compuesta por cuatro técnicas complementarias:

1. **Punto de Anclaje en el Nudillo del Índice (Landmark 5: `INDEX_FINGER_MCP`):** El cursor es guiado por la articulación metacarpofalángica del índice en lugar de la punta del dedo. Al ser un punto rígido de la estructura de la palma, permanece inmóvil durante la flexión de la pinza, desacoplando completamente el movimiento del cursor de la cinemática del pellizco.
2. **Filtro Adaptativo One Euro (Casiez et al., 2012):** Filtro pasa-bajas de primer orden con frecuencia de corte dinámica en función de la velocidad del movimiento. A baja velocidad opera a $f_{c_{\min}} = 1.0\text{ Hz}$ eliminando por completo el temblor en reposo; ante aceleraciones rápidas eleva la frecuencia de corte mediante el parámetro $\beta = 0.007$, suprimiendo el retraso o lag.
3. **Histéresis Dual con Distancia Normalizada:** La distancia pulgar-índice se normaliza en función del tamaño anatómico de la palma (Muñeca a Nudillo Medio), permitiendo una respuesta invariable a la distancia del operador respecto a la cámara. Se emplean dos umbrales diferenciados ($T_{\text{ON}} = 0.32$ para pulsar y $T_{\text{OFF}} = 0.45$ para soltar) con confirmación temporal de 2 cuadros, eliminando clics intermitentes o disparos espurios.
4. **Congelado de Cursor y Zona Muerta para Arrastre:** El cursor se fija en las coordenadas originales de apuntado ante la detección de pre-pellizco ($T_{\text{PRE}} = 0.52$). Para discriminar entre un clic estático y un arrastre (drag & drop), se establece una zona muerta de 15 px: solo desplazamientos superiores a este umbral activan el arrastre de elementos en el sistema operativo.

## Bibliografía

- Google Developers, "Hand landmarker guide," Google AI Edge, 2024. [Online]. Available: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker. [Accessed: Sep. 01, 2026].
- Google Developers, "Face landmarker guide," Google AI Edge, 2024. [Online]. Available: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker. [Accessed: Sep. 01, 2026].
- G. Casiez, N. Roussel, and D. Vogel, "1 € Filter: A Simple Speed-based Low-pass Filter for Noisy Input in Interactive Systems," in *Proc. ACM CHI Conference on Human Factors in Computing Systems*, Austin, TX, USA, 2012, pp. 2527-2530.
- Píldoras de programación, "Detección de manos y reproduccion de sonidos con MediaPipe," YouTube, Mar. 09, 2025. [Video en línea]. Disponible en: https://www.youtube.com/watch?v=h9AX0B3Oesw. [Accedido: Sep. 02, 2026].
- M. A. Rashad, "Filters for stability," FreeFaceMoCap, Dec. 25, 2021. [Online]. Available: https://mohamedalirashad.github.io/FreeFaceMoCap/2021-12-25-filters-for-stability/. [Accessed: Sep. 04, 2026].
- M. La Cascia, S. Sclaroff, and V. Athitsos, "Fast, reliable head tracking under large head rotation: A active appearance model-based approach," IEEE Transactions on Pattern Analysis and Machine Intelligence, vol. 22, no. 6, pp. 588-599, Jun. 2000. [Online]. Available: https://www.cs.bu.edu/groups/ivc/pubs/pami.22.4.pdf. [Accessed: Sep. 04, 2026].

