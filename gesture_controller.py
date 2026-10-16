"""
Controlador de Gestos para Visión Artificial.
Traduce gestos de mano detectados en acciones del sistema operativo (movimiento de cursor, clics, arrastre, scroll).

Técnicas avanzadas de precisión y estabilización implementadas:
1. Filtro One Euro (Casiez et al., CHI 2012):
   - Eliminación adaptativa del temblor en reposo sin añadir retraso al movimiento rápido.
2. Punto de Anclaje Estable (Landmark 5: Metacarpiano/Nudillo del Índice):
   - El cursor sigue el nudillo base del índice, desacoplando el movimiento del cursor de
     la flexión biomecánica involuntaria de la punta del dedo al pellizcar.
3. Distancia Normalizada respecto al tamaño anatómico de la mano:
   - Invariante a la distancia del usuario frente a la cámara (Landmark 0 a Landmark 9).
4. Histéresis Dual (T_ON / T_OFF):
   - Dos umbrales diferenciados para activar y soltar el pellizco, eliminando clics intermitentes.
5. Confirmación Temporal:
   - El pellizco debe mantenerse N cuadros consecutivos antes de dispararse, evitando falsos clics.
6. Congelamiento del Cursor (Anti-Drift):
   - Al detectar intención de pellizco (pre-pellizco), el cursor se congela en el objetivo.
7. Zona Muerta de Arrastre (Drag Deadzone):
   - El arrastre solo inicia si el movimiento supera un umbral tras pulsar, garantizando
     clics estáticos 100% limpios sin arrastres accidentales.
8. Soporte para Landmarks 3D (World Landmarks):
   - Uso opcional de coordenadas métricas 3D de MediaPipe para mitigar ruido de proyección 2D.
"""

import time
import math
import numpy as np
import pyautogui


class OneEuroFilter:
    """
    Filtro One Euro (Casiez, Roussel y Vogel, ACM CHI 2012).
    Filtro de paso bajo de primer orden con frecuencia de corte adaptativa basada en la velocidad.
    - A baja velocidad: frecuencia de corte baja -> elimina por completo el temblor y ruido.
    - A alta velocidad: frecuencia de corte alta -> reduce a cero la latencia de seguimiento.
    """

    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        """
        Args:
            min_cutoff: Frecuencia de corte mínima en Hz (controla el temblor en reposo).
            beta: Coeficiente de velocidad adaptativa (controla el retraso a alta velocidad).
            d_cutoff: Frecuencia de corte para el filtro de la derivada (velocidad).
        """
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)

        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    def _alpha(self, te, cutoff):
        """Calcula el factor de suavizado exponencial alpha = 1 / (1 + tau / te)."""
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

    def filter(self, x, timestamp=None):
        """
        Filtra una muestra escalar en el instante timestamp.
        
        Args:
            x: Valor numérico a filtrar.
            timestamp: Marca de tiempo en segundos (float). Si es None, usa time.time().
            
        Returns:
            float: Valor filtrado.
        """
        if timestamp is None:
            timestamp = time.time()

        if self.x_prev is None or self.t_prev is None:
            self.x_prev = float(x)
            self.dx_prev = 0.0
            self.t_prev = timestamp
            return float(x)

        te = timestamp - self.t_prev
        if te <= 1e-5:
            # Cuadro duplicado o delta de tiempo casi nulo
            return self.x_prev

        # 1. Derivada filtrada (estimación de velocidad)
        dx = (x - self.x_prev) / te
        a_d = self._alpha(te, self.d_cutoff)
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev

        # 2. Frecuencia de corte dinámica
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(te, cutoff)

        # 3. Filtrado de la señal
        x_hat = a * x + (1.0 - a) * self.x_prev

        # Guardar estado
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = timestamp

        return x_hat

    def reset(self):
        """Reinicia el estado del filtro."""
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None


class OneEuroFilter2D:
    """Filtro One Euro para coordenadas 2D (x, y) compartiendo marca de tiempo."""

    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.x_filter = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self.y_filter = OneEuroFilter(min_cutoff, beta, d_cutoff)

    def filter(self, x, y, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        fx = self.x_filter.filter(x, timestamp)
        fy = self.y_filter.filter(y, timestamp)
        return fx, fy

    def reset(self):
        self.x_filter.reset()
        self.y_filter.reset()


class CursorSmoother:
    """
    Filtro de suavizado para el cursor en pantalla.
    Soporta dos motores:
    - "one_euro": Filtro adaptativo One Euro (Casiez et al. 2012) - Recomendado.
    - "ema": Filtro de media móvil exponencial clásico (retrocompatibilidad).
    Incluye zona muerta (deadzone) para anular por completo micro-temblores en reposo.
    """

    def __init__(self, smoothing_factor=0.4, deadzone_px=0, filter_type=None,
                 min_cutoff=1.0, beta=0.007):
        """
        Args:
            smoothing_factor: Factor EMA entre 0 y 1 (usado si filter_type="ema").
            deadzone_px: Distancia en píxeles por debajo de la cual se ignora
                el movimiento (garantiza reposo absoluto). Por defecto 0.
            filter_type: "one_euro" o "ema". Si es None, usa "ema" si smoothing_factor
                fue configurado a un valor distinto del default, o "one_euro" en caso general.
            min_cutoff: Frecuencia de corte mínima para One Euro (Hz).
            beta: Coeficiente de velocidad adaptativa para One Euro.
        """
        self.smoothing_factor = smoothing_factor
        self.deadzone_px = deadzone_px

        # Decisión inteligente de motor para máxima compatibilidad
        if filter_type is None:
            if smoothing_factor != 0.4:
                self.filter_type = "ema"
            else:
                self.filter_type = "one_euro"
        else:
            self.filter_type = filter_type.lower()

        self._one_euro = OneEuroFilter2D(min_cutoff=min_cutoff, beta=beta)
        self._current_x = None
        self._current_y = None

    def smooth(self, target_x, target_y, timestamp=None):
        """
        Aplica suavizado a la posición destino.
        
        Args:
            target_x: Posición X destino (píxeles de pantalla).
            target_y: Posición Y destino (píxeles de pantalla).
            timestamp: Marca de tiempo en segundos (opcional).
            
        Returns:
            tuple[int, int]: Posición suavizada (x, y).
        """
        if self._current_x is None:
            self._current_x = float(target_x)
            self._current_y = float(target_y)
            self._one_euro.filter(target_x, target_y, timestamp)
            return int(self._current_x), int(self._current_y)

        dx = target_x - self._current_x
        dy = target_y - self._current_y
        dist = np.hypot(dx, dy)

        # Zona muerta: si el temblor es inferior al umbral, no mover el cursor
        if self.deadzone_px > 0 and dist < self.deadzone_px:
            return int(self._current_x), int(self._current_y)

        if self.filter_type == "one_euro":
            fx, fy = self._one_euro.filter(target_x, target_y, timestamp)
            self._current_x = fx
            self._current_y = fy
        else:
            # EMA clásico: new = old + (target - old) * (1 - smoothing)
            alpha = 1.0 - self.smoothing_factor
            self._current_x += dx * alpha
            self._current_y += dy * alpha

        return int(round(self._current_x)), int(round(self._current_y))

    def reset(self):
        """Resetea el filtro."""
        self._current_x = None
        self._current_y = None
        self._one_euro.reset()


class HysteresisPinchDetector:
    """
    Detector de pellizco con Histéresis Dual y Confirmación Temporal.
    
    Evita rebotes y falsos disparos utilizando dos umbrales sobre la distancia normalizada:
    - T_PRE: Congela el cursor ante la intención de pellizcar.
    - T_ON:  Umbral inferior para confirmar el contacto (cerrar pellizco).
    - T_OFF: Umbral superior para soltar el pellizco (abrir dedos).
    - Confirmación Temporal: Requiere N cuadros consecutivos bajo T_ON para confirmar el clic.
    """

    def __init__(self, t_on=0.32, t_off=0.45, t_pre=0.52, confirm_frames=2):
        """
        Args:
            t_on: Umbral normalizado para activar el pellizco (d < t_on).
            t_off: Umbral normalizado para liberar el pellizco (d > t_off).
            t_pre: Umbral normalizado para precongelar el cursor (d < t_pre).
            confirm_frames: Cuadros consecutivos requeridos para validar el estado.
        """
        self.t_on = t_on
        self.t_off = t_off
        self.t_pre = t_pre
        self.confirm_frames = max(1, int(confirm_frames))

        self.is_pinching = False
        self.is_pre_pinching = False
        self._consecutive_on_frames = 0
        self._consecutive_off_frames = 0

    def update(self, normalized_dist):
        """
        Actualiza el estado con la distancia normalizada actual.
        
        Args:
            normalized_dist: Distancia entre dedos dividida por el tamaño de referencia de la mano.
            
        Returns:
            dict: Estado del detector conteniendo:
                  "pinching": bool (si el pellizco está activo).
                  "pre_pinching": bool (si se debe congelar el cursor).
                  "just_pressed": bool (True en el cuadro exacto donde se activa el pellizco).
                  "just_released": bool (True en el cuadro exacto donde se libera el pellizco).
                  "normalized_dist": float.
        """
        just_pressed = False
        just_released = False

        # Intención de pellizco (pre-pellizco para congelar cursor)
        self.is_pre_pinching = (normalized_dist < self.t_pre) or self.is_pinching

        if not self.is_pinching:
            if normalized_dist < self.t_on:
                self._consecutive_on_frames += 1
                if self._consecutive_on_frames >= self.confirm_frames:
                    self.is_pinching = True
                    just_pressed = True
                    self._consecutive_off_frames = 0
            else:
                self._consecutive_on_frames = 0
        else:
            if normalized_dist > self.t_off:
                self._consecutive_off_frames += 1
                if self._consecutive_off_frames >= self.confirm_frames:
                    self.is_pinching = False
                    just_released = True
                    self._consecutive_on_frames = 0
            else:
                self._consecutive_off_frames = 0

        return {
            "pinching": self.is_pinching,
            "pre_pinching": self.is_pre_pinching,
            "just_pressed": just_pressed,
            "just_released": just_released,
            "normalized_dist": normalized_dist
        }

    def reset(self):
        """Reinicia el detector."""
        self.is_pinching = False
        self.is_pre_pinching = False
        self._consecutive_on_frames = 0
        self._consecutive_off_frames = 0


class ClickDebouncer:
    """
    Sistema de debounce temporal para clics sostenidos y cooldown.
    """

    def __init__(self, hold_time_ms=150, cooldown_ms=300):
        self._hold_time = hold_time_ms / 1000.0
        self._cooldown = cooldown_ms / 1000.0
        self._pinch_start_time = None
        self._last_click_time = 0.0
        self._clicked = False

    def update(self, is_pinching):
        now = time.time()

        if not is_pinching:
            self._pinch_start_time = None
            self._clicked = False
            return False

        if self._pinch_start_time is None:
            self._pinch_start_time = now
            return False

        held_duration = now - self._pinch_start_time
        if held_duration < self._hold_time:
            return False

        if (now - self._last_click_time) < self._cooldown:
            return False

        if self._clicked:
            return False

        self._last_click_time = now
        self._clicked = True
        return True

    def reset(self):
        self._pinch_start_time = None
        self._clicked = False


class GestureController:
    """
    Controlador principal que traduce gestos detectados en acciones del SO.
    
    Implementa la arquitectura de 4 Pilares de Precisión:
    1. Anclaje en Landmark 5 (Nudillo del Índice): Movimiento desacoplado del pellizco.
    2. Suavizado One Euro Filter sobre el anclaje: Cero temblor en reposo + respuesta inmediata.
    3. Histéresis Dual con Distancia Normalizada: Clics consistentes a cualquier distancia de cámara.
    4. Congelamiento del Cursor + Zona Muerta de Arrastre: Clics estáticos sin desplazamiento
       y soporte de arrastre intencional.
    """

    # Constantes anatómicas de MediaPipe
    WRIST_ID = 0
    THUMB_TIP_ID = 4
    INDEX_MCP_ID = 5         # Nudillo base del índice (ANCLAJE ESTABLE)
    INDEX_TIP_ID = 8         # Punta del índice
    MIDDLE_MCP_ID = 9        # Base del dedo medio (referencia para tamaño de mano)
    MIDDLE_TIP_ID = 12       # Punta del dedo medio

    # Parámetros por defecto
    DEFAULT_ANCHOR_ID = INDEX_MCP_ID
    DEFAULT_T_ON = 0.32
    DEFAULT_T_OFF = 0.45
    DEFAULT_T_PRE = 0.52
    DEFAULT_DRAG_DEADZONE_PX = 15      # Píxeles de movimiento de cámara para activar arrastre
    DEFAULT_POST_CLICK_FREEZE_S = 0.20 # Tiempo de congelamiento tras soltar

    def __init__(self, screen_width, screen_height, execute_actions=True,
                 smoothing_factor=0.4, hold_time_ms=150, cooldown_ms=300,
                 deadzone_px=3, pre_pinch_threshold=58, pinch_threshold=38,
                 post_click_freeze_s=0.20, anchor_landmark_id=INDEX_MCP_ID,
                 t_on=0.32, t_off=0.45, t_pre=0.52, drag_deadzone_px=15,
                 min_cutoff=1.0, beta=0.007, confirm_frames=2,
                 move_cursor=True):
        """
        Inicializa el controlador con todos los parámetros de estabilización.
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.execute_actions = execute_actions
        self.deadzone_px = deadzone_px
        self.pre_pinch_threshold = pre_pinch_threshold
        self.pinch_threshold = pinch_threshold
        self.post_click_freeze_s = post_click_freeze_s
        self.anchor_landmark_id = anchor_landmark_id
        self.drag_deadzone_px = drag_deadzone_px
        self.move_cursor = move_cursor

        # Filtro de suavizado (One Euro Filter por defecto)
        self.smoother = CursorSmoother(
            smoothing_factor=smoothing_factor,
            deadzone_px=deadzone_px,
            filter_type="one_euro",
            min_cutoff=min_cutoff,
            beta=beta
        )

        # Detectores de histéresis normalizada para clic izquierdo y derecho
        self.left_pinch_detector = HysteresisPinchDetector(
            t_on=t_on, t_off=t_off, t_pre=t_pre, confirm_frames=confirm_frames
        )
        self.right_pinch_detector = HysteresisPinchDetector(
            t_on=t_on, t_off=t_off, t_pre=t_pre, confirm_frames=confirm_frames
        )

        # Debouncers temporales
        self.left_click_debouncer = ClickDebouncer(hold_time_ms, cooldown_ms)
        self.right_click_debouncer = ClickDebouncer(hold_time_ms, cooldown_ms)

        self._current_mode = "REPOSO"
        self._last_scroll_y = None
        self._last_smooth_x = 0
        self._last_smooth_y = 0

        # Estado de congelamiento de posición (anti-drift)
        self._is_click_locked = False
        self._locked_cursor_x = None
        self._locked_cursor_y = None
        self._post_click_freeze_until = 0.0

        # Estado de arrastre (drag)
        self._is_dragging = False
        self._drag_start_anchor_pos = None

    @property
    def is_click_locked(self):
        """Indica si la posición del cursor está actualmente congelada."""
        return self._is_click_locked

    @property
    def locked_position(self):
        """Retorna (x, y) donde el cursor está congelado, o None."""
        if self._is_click_locked:
            return (self._locked_cursor_x, self._locked_cursor_y)
        return None

    @property
    def is_dragging(self):
        """Indica si el sistema está ejecutando un arrastre activo (mouseDown)."""
        return self._is_dragging

    @property
    def current_mode(self):
        """Modo de operación actual."""
        return self._current_mode

    def _calculate_hand_size(self, landmarks, frame_w, frame_h):
        """
        Calcula el tamaño anatómico de referencia de la mano (Muñeca a Nudillo Medio).
        Esta distancia es fija e independiente de si los dedos están abiertos o doblados.
        """
        wrist = landmarks[self.WRIST_ID]
        middle_mcp = landmarks[self.MIDDLE_MCP_ID]

        wx, wy = wrist.x * frame_w, wrist.y * frame_h
        mx, my = middle_mcp.x * frame_w, middle_mcp.y * frame_h

        hand_size = np.hypot(mx - wx, my - wy)
        # Si los landmarks de referencia son inválidos o nulos (ej. mocks incompletos),
        # retornar tamaño estimado por defecto de 100 px para evitar división por cero.
        return hand_size if hand_size >= 15.0 else 100.0

    def _get_active_bounds(self, frame_w, frame_h, frame_margin):
        """
        Determina los límites (x_min, x_max, y_min, y_max) del encuadre
        que se proyectan sobre la pantalla completa del usuario.
        Soporta escalares, tuplas (x_min, x_max, y_min, y_max) y diccionarios.
        """
        if isinstance(frame_margin, (tuple, list)):
            if len(frame_margin) == 4:
                return frame_margin[0], frame_margin[1], frame_margin[2], frame_margin[3]
            elif len(frame_margin) == 2:
                mx, my = frame_margin
                return mx, frame_w - mx, my, frame_h - my
        elif isinstance(frame_margin, dict):
            x_min = frame_margin.get("x_min", frame_margin.get("left", 100))
            x_max = frame_margin.get("x_max", frame_w - frame_margin.get("right", 100))
            y_min = frame_margin.get("y_min", frame_margin.get("top", 100))
            y_max = frame_margin.get("y_max", frame_h - frame_margin.get("bottom", 100))
            return x_min, x_max, y_min, y_max

        m = float(frame_margin)
        return m, frame_w - m, m, frame_h - m

    def process_gesture(self, fingers, landmarks, frame_w, frame_h, frame_margin,
                        handedness="Right", world_landmarks=None, timestamp=None,
                        external_cursor_pos=None):
        """
        Procesa el gesto detectado y ejecuta la acción estabilizada correspondiente.
        """
        result = {
            "mode": "REPOSO",
            "moved_cursor": False,
            "cursor_locked": False,
            "clicked": False,
            "right_clicked": False,
            "is_dragging": self._is_dragging,
            "drag_ended": False,
            "scrolled": False,
            "scroll_amount": 0,
            "cursor_x": self._last_smooth_x,
            "cursor_y": self._last_smooth_y,
            "normalized_dist": 1.0,
            "hand_size": 100.0
        }

        if fingers is None or landmarks is None:
            self._current_mode = "REPOSO"
            self.smoother.reset()
            self.left_pinch_detector.reset()
            self.right_pinch_detector.reset()
            self._last_scroll_y = None
            self._is_click_locked = False
            if self._is_dragging:
                if self.execute_actions:
                    pyautogui.mouseUp()
                self._is_dragging = False
                result["drag_ended"] = True
            if external_cursor_pos is not None and not self.move_cursor:
                self._last_smooth_x = int(external_cursor_pos[0])
                self._last_smooth_y = int(external_cursor_pos[1])
                result["cursor_x"] = self._last_smooth_x
                result["cursor_y"] = self._last_smooth_y
            self.left_click_debouncer.reset()
            self.right_click_debouncer.reset()
            return result

        if hasattr(landmarks, "landmark"):
            landmarks = landmarks.landmark

        # Determinar modo basado en los dedos levantados
        mode = self._determine_mode(fingers)
        self._current_mode = mode
        result["mode"] = mode

        # Puntos clave de la mano
        thumb_tip = landmarks[self.THUMB_TIP_ID]
        index_tip = landmarks[self.INDEX_TIP_ID]
        middle_tip = landmarks[self.MIDDLE_TIP_ID]

        # Punto de anclaje para mover el cursor (Landmark 5: Nudillo del índice)
        anchor_lm = landmarks[self.anchor_landmark_id] if len(landmarks) > self.anchor_landmark_id else index_tip
        ax, ay = int(anchor_lm.x * frame_w), int(anchor_lm.y * frame_h)

        ix, iy = int(index_tip.x * frame_w), int(index_tip.y * frame_h)
        tx, ty = int(thumb_tip.x * frame_w), int(thumb_tip.y * frame_h)
        mx, my = int(middle_tip.x * frame_w), int(middle_tip.y * frame_h)

        # Distancia en píxeles de cámara
        dist_thumb_index_px = np.hypot(ix - tx, iy - ty)
        dist_thumb_middle_px = np.hypot(mx - tx, my - ty)

        # Tamaño de referencia anatómico de la mano
        hand_size = self._calculate_hand_size(landmarks, frame_w, frame_h)
        result["hand_size"] = hand_size

        # Distancia normalizada
        norm_dist_thumb_index = dist_thumb_index_px / hand_size
        norm_dist_thumb_middle = dist_thumb_middle_px / hand_size
        result["normalized_dist"] = norm_dist_thumb_index

        # En modo híbrido (move_cursor=False), la mano no apunta: permitir pinza relajada
        # (Pfeuffer et al., SUI '17; Chatterjee et al., ICMI '15) sin exigir índice rígido [0, 1, 0, 0, 0],
        # preservando el gesto ✌️ de SCROLL sin que el pulgar doblado lo secuestre hacia PUNTERO.
        if not self.move_cursor and fingers != [0, 0, 0, 0, 0]:
            is_peace_scroll = (
                fingers == [0, 1, 1, 0, 0]
                or (
                    fingers == [1, 1, 1, 0, 0]
                    and norm_dist_thumb_middle >= self.right_pinch_detector.t_pre
                    and norm_dist_thumb_index >= self.left_pinch_detector.t_pre
                )
            )
            if is_peace_scroll and not self._is_dragging:
                mode = "SCROLL"
            elif (
                norm_dist_thumb_index < self.left_pinch_detector.t_pre
                or self.left_pinch_detector.is_pinching
                or self._is_dragging
            ):
                mode = "PUNTERO"
            elif mode != "SCROLL" and (
                norm_dist_thumb_middle < self.right_pinch_detector.t_pre
                or self.right_pinch_detector.is_pinching
            ):
                mode = "CLIC_DERECHO"
            self._current_mode = mode
            result["mode"] = mode

        now = timestamp if timestamp is not None else time.time()
        x_min, x_max, y_min, y_max = self._get_active_bounds(frame_w, frame_h, frame_margin)

        # =====================================================================
        # MODO PUNTERO
        # =====================================================================
        if mode == "PUNTERO":
            # Actualizar detector de histéresis normalizada
            h_state = self.left_pinch_detector.update(norm_dist_thumb_index)
            is_pinching = h_state["pinching"]
            is_pre_pinching = h_state["pre_pinching"]
            in_post_freeze = now < self._post_click_freeze_until

            # Respaldo con umbrales en píxeles únicamente si hand_size es degenerado (< 25px, ej. mocks incompletos)
            if hand_size < 25.0:
                if dist_thumb_index_px < self.pinch_threshold:
                    is_pinching = True
                if dist_thumb_index_px < self.pre_pinch_threshold:
                    is_pre_pinching = True

            # Gestión de Arrastre (Drag) vs Clic Estático
            if is_pinching:
                if self._drag_start_anchor_pos is None:
                    self._drag_start_anchor_pos = (ax, ay)

                dist_from_pinch_start = np.hypot(
                    ax - self._drag_start_anchor_pos[0],
                    ay - self._drag_start_anchor_pos[1]
                )

                # Si el usuario desplaza intencionalmente la mano más allá de la zona muerta
                if dist_from_pinch_start > self.drag_deadzone_px:
                    if not self._is_dragging:
                        self._is_dragging = True
                        if self.execute_actions:
                            pyautogui.mouseDown()
            else:
                self._drag_start_anchor_pos = None

            # Determinar si el cursor debe estar congelado en la posición de apuntado
            should_freeze = (is_pre_pinching or is_pinching or in_post_freeze) and (not self._is_dragging)

            if should_freeze:
                if not self._is_click_locked:
                    self._is_click_locked = True
                    # Si no teníamos posición suavizada previa, inicializarla con la vista o el anclaje
                    if self._last_smooth_x == 0 and self._last_smooth_y == 0:
                        if external_cursor_pos is not None:
                            self._last_smooth_x = int(external_cursor_pos[0])
                            self._last_smooth_y = int(external_cursor_pos[1])
                        else:
                            raw_x = np.interp(ax, (x_min, x_max), (0, self.screen_width))
                            raw_y = np.interp(ay, (y_min, y_max), (0, self.screen_height))
                            self._last_smooth_x, self._last_smooth_y = self.smoother.smooth(raw_x, raw_y, now)
                    self._locked_cursor_x = self._last_smooth_x
                    self._locked_cursor_y = self._last_smooth_y

                cursor_x = self._locked_cursor_x
                cursor_y = self._locked_cursor_y
                result["cursor_locked"] = True
                result["moved_cursor"] = False
            else:
                if self._is_click_locked:
                    self.smoother.reset()
                    self._is_click_locked = False

                if external_cursor_pos is not None and not self.move_cursor:
                    smooth_x = int(external_cursor_pos[0])
                    smooth_y = int(external_cursor_pos[1])
                    self._last_smooth_x = smooth_x
                    self._last_smooth_y = smooth_y
                    cursor_x = smooth_x
                    cursor_y = smooth_y
                    result["cursor_locked"] = False
                    result["moved_cursor"] = False
                else:
                    raw_x = np.interp(ax, (x_min, x_max), (0, self.screen_width))
                    raw_y = np.interp(ay, (y_min, y_max), (0, self.screen_height))
                    raw_x = int(np.clip(raw_x, 0, self.screen_width - 1))
                    raw_y = int(np.clip(raw_y, 0, self.screen_height - 1))

                    smooth_x, smooth_y = self.smoother.smooth(raw_x, raw_y, now)
                    self._last_smooth_x = smooth_x
                    self._last_smooth_y = smooth_y
                    cursor_x = smooth_x
                    cursor_y = smooth_y
                    result["cursor_locked"] = False
                    result["moved_cursor"] = self.move_cursor

                    if self.execute_actions and self.move_cursor:
                        pyautogui.moveTo(smooth_x, smooth_y)

            result["cursor_x"] = cursor_x
            result["cursor_y"] = cursor_y
            result["is_dragging"] = self._is_dragging

            # Finalización de arrastre al soltar el pellizco
            if h_state["just_released"] and self._is_dragging:
                if self.execute_actions:
                    pyautogui.mouseUp()
                self._is_dragging = False
                result["drag_ended"] = True
                self._post_click_freeze_until = now + self.post_click_freeze_s

            # Ejecución de clic izquierdo (con debounce y confirmación)
            should_click = self.left_click_debouncer.update(is_pinching)
            if should_click and not self._is_dragging:
                result["clicked"] = True
                self._post_click_freeze_until = now + self.post_click_freeze_s
                if self.execute_actions:
                    pyautogui.click(x=cursor_x, y=cursor_y)

            self.right_pinch_detector.reset()
            self.right_click_debouncer.reset()
            self._last_scroll_y = None

        # =====================================================================
        # MODO SCROLL
        # =====================================================================
        elif mode == "SCROLL":
            self._is_click_locked = False
            if self._is_dragging:
                if self.execute_actions:
                    pyautogui.mouseUp()
                self._is_dragging = False
                result["drag_ended"] = True

            if external_cursor_pos is not None and not self.move_cursor:
                # Scroll controlado por la VISTA mientras la mano sostiene ✌️ quieta como "pedal":
                # Mirar por encima de la banda central desliza hacia arriba; mirar por debajo desliza hacia abajo.
                result["cursor_locked"] = True
                result["moved_cursor"] = False
                gaze_y = float(external_cursor_pos[1])
                center_y = self.screen_height / 2.0
                deadzone_y = self.screen_height * 0.12
                scroll_amount = 0

                if gaze_y < center_y - deadzone_y:
                    span = max(1.0, center_y - deadzone_y)
                    norm_offset = min(1.0, (center_y - deadzone_y - gaze_y) / span)
                    scroll_amount = int(round(20 + 70 * norm_offset))
                elif gaze_y > center_y + deadzone_y:
                    span = max(1.0, self.screen_height - (center_y + deadzone_y))
                    norm_offset = min(1.0, (gaze_y - (center_y + deadzone_y)) / span)
                    scroll_amount = -int(round(20 + 70 * norm_offset))

                if scroll_amount != 0:
                    result["scrolled"] = True
                    result["scroll_amount"] = scroll_amount
                    if self.execute_actions:
                        pyautogui.scroll(scroll_amount)
            else:
                avg_y = (iy + my) / 2.0
                if self._last_scroll_y is not None:
                    delta_y = self._last_scroll_y - avg_y
                    if abs(delta_y) > 5:
                        scroll_amount = int(delta_y * 2)
                        result["scrolled"] = True
                        result["scroll_amount"] = scroll_amount
                        if self.execute_actions:
                            pyautogui.scroll(scroll_amount)
                self._last_scroll_y = avg_y

            self.left_pinch_detector.reset()
            self.right_pinch_detector.reset()
            self.left_click_debouncer.reset()
            self.right_click_debouncer.reset()
            result["cursor_x"] = self._last_smooth_x
            result["cursor_y"] = self._last_smooth_y

        # =====================================================================
        # MODO CLIC DERECHO
        # =====================================================================
        elif mode == "CLIC_DERECHO":
            h_state_r = self.right_pinch_detector.update(norm_dist_thumb_middle)
            is_pinching_r = h_state_r["pinching"]
            is_pre_pinching_r = h_state_r["pre_pinching"]
            in_post_freeze = now < self._post_click_freeze_until

            if hand_size < 25.0:
                if dist_thumb_middle_px < self.pinch_threshold:
                    is_pinching_r = True
                if dist_thumb_middle_px < self.pre_pinch_threshold:
                    is_pre_pinching_r = True

            should_freeze = is_pre_pinching_r or is_pinching_r or in_post_freeze

            if should_freeze:
                if not self._is_click_locked:
                    self._is_click_locked = True
                    if self._last_smooth_x == 0 and self._last_smooth_y == 0:
                        if external_cursor_pos is not None:
                            self._last_smooth_x = int(external_cursor_pos[0])
                            self._last_smooth_y = int(external_cursor_pos[1])
                        else:
                            raw_x = np.interp(ax, (x_min, x_max), (0, self.screen_width))
                            raw_y = np.interp(ay, (y_min, y_max), (0, self.screen_height))
                            self._last_smooth_x, self._last_smooth_y = self.smoother.smooth(raw_x, raw_y, now)
                    self._locked_cursor_x = self._last_smooth_x
                    self._locked_cursor_y = self._last_smooth_y

                cursor_x = self._locked_cursor_x
                cursor_y = self._locked_cursor_y
                result["cursor_locked"] = True
                result["moved_cursor"] = False
            else:
                if self._is_click_locked:
                    self.smoother.reset()
                    self._is_click_locked = False

                if external_cursor_pos is not None and not self.move_cursor:
                    smooth_x = int(external_cursor_pos[0])
                    smooth_y = int(external_cursor_pos[1])
                    self._last_smooth_x = smooth_x
                    self._last_smooth_y = smooth_y
                    cursor_x = smooth_x
                    cursor_y = smooth_y
                    result["cursor_locked"] = False
                    result["moved_cursor"] = False
                else:
                    raw_x = np.interp(ax, (x_min, x_max), (0, self.screen_width))
                    raw_y = np.interp(ay, (y_min, y_max), (0, self.screen_height))
                    raw_x = int(np.clip(raw_x, 0, self.screen_width - 1))
                    raw_y = int(np.clip(raw_y, 0, self.screen_height - 1))

                    smooth_x, smooth_y = self.smoother.smooth(raw_x, raw_y, now)
                    self._last_smooth_x = smooth_x
                    self._last_smooth_y = smooth_y
                    cursor_x = smooth_x
                    cursor_y = smooth_y
                    result["cursor_locked"] = False
                    result["moved_cursor"] = self.move_cursor

                    if self.execute_actions and self.move_cursor:
                        pyautogui.moveTo(smooth_x, smooth_y)

            result["cursor_x"] = cursor_x
            result["cursor_y"] = cursor_y

            should_right_click = self.right_click_debouncer.update(is_pinching_r)
            if should_right_click:
                result["right_clicked"] = True
                self._post_click_freeze_until = now + self.post_click_freeze_s
                if self.execute_actions:
                    pyautogui.rightClick(x=cursor_x, y=cursor_y)

            self.left_pinch_detector.reset()
            self.left_click_debouncer.reset()
            self._last_scroll_y = None

        # =====================================================================
        # MODO REPOSO
        # =====================================================================
        else:
            self._is_click_locked = False
            if self._is_dragging:
                if self.execute_actions:
                    pyautogui.mouseUp()
                self._is_dragging = False
                result["drag_ended"] = True

            if external_cursor_pos is not None and not self.move_cursor:
                self._last_smooth_x = int(external_cursor_pos[0])
                self._last_smooth_y = int(external_cursor_pos[1])
                result["cursor_x"] = self._last_smooth_x
                result["cursor_y"] = self._last_smooth_y

            self.smoother.reset()
            self.left_pinch_detector.reset()
            self.right_pinch_detector.reset()
            self.left_click_debouncer.reset()
            self.right_click_debouncer.reset()
            self._last_scroll_y = None

        return result

    def _determine_mode(self, fingers):
        """
        Determina el modo de operación basado en los dedos levantados.
        """
        if fingers is None:
            return "REPOSO"

        pulgar, indice, medio, anular, menique = fingers

        if fingers == [0, 0, 0, 0, 0]:
            return "REPOSO"

        if fingers == [1, 1, 1, 1, 1]:
            return "REPOSO"

        # Solo índice levantado (con o sin pulgar)
        if indice and not medio and not anular and not menique:
            return "PUNTERO"

        # Índice + medio (sin anular ni meñique ni pulgar) -> scroll
        if indice and medio and not anular and not menique and not pulgar:
            return "SCROLL"

        # Pulgar + índice + medio -> clic derecho
        if pulgar and indice and medio and not anular and not menique:
            return "CLIC_DERECHO"

        return "REPOSO"
