"""
Módulo de Bloqueo de Usuario Activo para entornos multi-persona.

Implementa una máquina de estados que decide quién tiene el control del sistema
cuando hay varias personas en el encuadre de la cámara.

Estados:
    INACTIVO  → Nadie controla. Esperando gesto de activación.
    ACTIVANDO → Se detectó palma abierta, esperando confirmación temporal.
    ACTIVO    → Usuario bloqueado. Solo su mano genera acciones.
    PERDIDO   → La mano del usuario desapareció. Esperando reaparición.
    PAUSADO   → Usuario pidió pausa con puño cerrado sostenido.
"""

import time
import math
import cv2
import numpy as np


class UserLock:
    """
    Máquina de estados para aislar al usuario activo en entornos
    con múltiples personas.

    Estrategia combinada:
    1. Gesto de activación (palma abierta sostenida)
    2. Bloqueo por continuidad espacial (centroide frame-a-frame)
    3. Liberación automática por timeout
    """

    def __init__(
        self,
        activation_time_s=2.0,
        reactivation_time_s=1.0,
        lost_timeout_s=3.0,
        pause_timeout_s=10.0,
        pause_gesture_time_s=2.0,
        continuity_threshold_px=150
    ):
        """
        Args:
            activation_time_s: Segundos de palma abierta para activar.
            reactivation_time_s: Segundos para reactivar desde pausa.
            lost_timeout_s: Segundos sin mano antes de volver a INACTIVO.
            pause_timeout_s: Segundos en pausa antes de volver a INACTIVO.
            pause_gesture_time_s: Segundos de puño cerrado para pausar.
            continuity_threshold_px: Distancia máxima (px) para considerar la misma mano.
        """
        self._activation_time = activation_time_s
        self._reactivation_time = reactivation_time_s
        self._lost_timeout = lost_timeout_s
        self._pause_timeout = pause_timeout_s
        self._pause_gesture_time = pause_gesture_time_s
        self._continuity_threshold = continuity_threshold_px

        # Estado interno
        self._state = "INACTIVO"
        self._locked_centroid = None      # (x, y) en píxeles del frame
        self._locked_handedness = None    # "Right" o "Left"
        self._activation_start_time = None
        self._lost_start_time = None
        self._pause_start_time = None
        self._pause_gesture_start = None
        self._activation_progress = 0.0

    @property
    def state(self):
        """Estado actual de la máquina de estados."""
        return self._state

    @property
    def activation_progress(self):
        """Progreso de activación (0.0 a 1.0)."""
        return self._activation_progress

    def update(self, all_hands, all_handedness, all_fingers, frame_w, frame_h, user_present=False):
        """
        Actualiza el estado del bloqueo de usuario.

        Args:
            all_hands: Lista de landmarks de todas las manos detectadas, o None.
            all_handedness: Lista de handedness de cada mano, o None.
            all_fingers: Lista de listas [pulgar, índice, medio, anular, meñique] para cada mano.
            frame_w: Ancho del frame en píxeles.
            frame_h: Alto del frame en píxeles.
            user_present: True si el rostro del usuario activo sigue frente a la cámara
                          (evita expirar la sesión cuando baja la mano para descansar).

        Returns:
            dict: {
                "state": str,
                "active_hand": landmarks o None,
                "active_fingers": [int]*5 o None,
                "handedness": str o None,
                "activation_progress": float (0.0 a 1.0)
            }
        """
        now = time.time()
        hands = all_hands if all_hands else []
        handedness_list = all_handedness if all_handedness else []
        fingers_list = all_fingers if all_fingers else []

        result = {
            "state": self._state,
            "active_hand": None,
            "active_fingers": None,
            "handedness": None,
            "activation_progress": 0.0
        }

        # --- INACTIVO: esperando gesto de activación ---
        if self._state == "INACTIVO":
            result = self._handle_inactive(hands, handedness_list, fingers_list, frame_w, frame_h, now)

        # --- ACTIVANDO: palma abierta detectada, contando tiempo ---
        elif self._state == "ACTIVANDO":
            result = self._handle_activating(hands, handedness_list, fingers_list, frame_w, frame_h, now)

        # --- ACTIVO: usuario bloqueado, seleccionar mano más cercana ---
        elif self._state == "ACTIVO":
            result = self._handle_active(hands, handedness_list, fingers_list, frame_w, frame_h, now)

        # --- PERDIDO: mano desapareció, esperando reaparición ---
        elif self._state == "PERDIDO":
            result = self._handle_lost(
                hands, handedness_list, fingers_list, frame_w, frame_h, now,
                user_present=user_present
            )

        # --- PAUSADO: usuario pidió pausa ---
        elif self._state == "PAUSADO":
            result = self._handle_paused(hands, handedness_list, fingers_list, frame_w, frame_h, now)

        result["state"] = self._state
        return result

    # --- Handlers de cada estado ---

    def _handle_inactive(self, hands, handedness_list, fingers_list, fw, fh, now):
        result = self._empty_result()

        candidate_palms = []
        for i, (hand, fingers) in enumerate(zip(hands, fingers_list)):
            if self._is_palm_open(fingers):
                area = self._calculate_hand_area(hand, fw, fh)
                candidate_palms.append((area, i, hand))

        if candidate_palms:
            # Seleccionar la mano más grande (más cercana a la cámara)
            candidate_palms.sort(key=lambda item: item[0], reverse=True)
            _, best_idx, best_hand = candidate_palms[0]

            self._state = "ACTIVANDO"
            self._activation_start_time = now
            self._locked_centroid = self._calculate_centroid(best_hand, fw, fh)
            if best_idx < len(handedness_list):
                self._locked_handedness = handedness_list[best_idx].classification[0].label
            self._activation_progress = 0.01
            result["activation_progress"] = self._activation_progress

        return result

    def _handle_activating(self, hands, handedness_list, fingers_list, fw, fh, now):
        result = self._empty_result()

        # Buscar la mano más cercana al centroide de activación
        closest_hand, closest_idx, dist = self._find_closest_hand(hands, fw, fh)

        if closest_hand is None or closest_idx >= len(fingers_list) or dist > self._continuity_threshold:
            # Mano desapareció o se alejó demasiado durante activación → cancelar
            self._state = "INACTIVO"
            self._activation_start_time = None
            self._activation_progress = 0.0
            return result

        fingers = fingers_list[closest_idx]

        if not self._is_palm_open(fingers):
            # Gesto interrumpido → cancelar
            self._state = "INACTIVO"
            self._activation_start_time = None
            self._activation_progress = 0.0
            return result

        # Calcular progreso
        elapsed = now - self._activation_start_time
        self._activation_progress = min(elapsed / self._activation_time, 1.0)
        result["activation_progress"] = self._activation_progress

        if elapsed >= self._activation_time:
            # ¡Activación completa!
            self._state = "ACTIVO"
            self._locked_centroid = self._calculate_centroid(closest_hand, fw, fh)
            if closest_idx < len(handedness_list):
                self._locked_handedness = handedness_list[closest_idx].classification[0].label
            self._activation_progress = 1.0
            self._activation_start_time = None
            result["active_hand"] = closest_hand
            result["active_index"] = closest_idx
            result["active_fingers"] = fingers
            result["handedness"] = self._locked_handedness
            result["activation_progress"] = 1.0

        return result

    def _handle_active(self, hands, handedness_list, fingers_list, fw, fh, now):
        result = self._empty_result()

        if not hands:
            # Mano desapareció → estado PERDIDO
            self._state = "PERDIDO"
            self._lost_start_time = now
            return result

        # Encontrar la mano más cercana al centroide bloqueado
        closest_hand, closest_idx, dist = self._find_closest_hand(hands, fw, fh)

        if closest_hand is None or dist > self._continuity_threshold:
            # La mano más cercana está demasiado lejos → PERDIDO
            self._state = "PERDIDO"
            self._lost_start_time = now
            return result

        # Actualizar centroide
        self._locked_centroid = self._calculate_centroid(closest_hand, fw, fh)
        if closest_idx < len(handedness_list):
            self._locked_handedness = handedness_list[closest_idx].classification[0].label

        fingers = fingers_list[closest_idx] if closest_idx < len(fingers_list) else None

        # Verificar gesto de pausa (puño cerrado sostenido)
        if fingers and self._is_fist(fingers):
            if self._pause_gesture_start is None:
                self._pause_gesture_start = now
            elif (now - self._pause_gesture_start) >= self._pause_gesture_time:
                self._state = "PAUSADO"
                self._pause_start_time = now
                self._pause_gesture_start = None
                return result
        else:
            self._pause_gesture_start = None

        result["active_hand"] = closest_hand
        result["active_index"] = closest_idx
        result["active_fingers"] = fingers
        result["handedness"] = self._locked_handedness
        return result

    def _handle_lost(self, hands, handedness_list, fingers_list, fw, fh, now, user_present=False):
        result = self._empty_result()

        if hands:
            # Buscar si la mano reapareció cerca o si es la única mano con la misma lateralidad
            # (permite apoyar la mano en el escritorio y retomarla en una posición baja de descanso)
            closest_hand, closest_idx, dist = self._find_closest_hand(hands, fw, fh)
            candidate_handedness = (
                handedness_list[closest_idx].classification[0].label
                if closest_idx is not None and closest_idx < len(handedness_list)
                else None
            )
            same_handedness = (
                self._locked_handedness is None
                or candidate_handedness == self._locked_handedness
            )
            can_resume = closest_hand is not None and (
                dist <= self._continuity_threshold
                or (len(hands) == 1 and same_handedness)
            )
            if can_resume:
                # ¡Reaparición! Volver a ACTIVO
                self._state = "ACTIVO"
                self._locked_centroid = self._calculate_centroid(closest_hand, fw, fh)
                if candidate_handedness is not None:
                    self._locked_handedness = candidate_handedness
                fingers = fingers_list[closest_idx] if closest_idx < len(fingers_list) else None
                result["active_hand"] = closest_hand
                result["active_index"] = closest_idx
                result["active_fingers"] = fingers
                result["handedness"] = self._locked_handedness
                return result

        # Mientras el rostro del usuario siga presente, mantener viva la espera de la mano en descanso
        if user_present:
            self._lost_start_time = now
            return result

        # Verificar timeout cuando el usuario ya no está presente
        if (now - self._lost_start_time) >= self._lost_timeout:
            self._state = "INACTIVO"
            self._locked_centroid = None
            self._locked_handedness = None

        return result

    def _handle_paused(self, hands, handedness_list, fingers_list, fw, fh, now):
        result = self._empty_result()

        # Verificar timeout de pausa
        if (now - self._pause_start_time) >= self._pause_timeout:
            self._state = "INACTIVO"
            self._locked_centroid = None
            return result

        # Verificar gesto de reactivación (palma abierta) en la mano más cercana
        if hands:
            closest_hand, closest_idx, dist = self._find_closest_hand(hands, fw, fh)
            if closest_hand is not None and closest_idx < len(fingers_list) and dist <= self._continuity_threshold:
                fingers = fingers_list[closest_idx]
                if self._is_palm_open(fingers):
                    if self._activation_start_time is None:
                        self._activation_start_time = now
                    elif (now - self._activation_start_time) >= self._reactivation_time:
                        # Reactivación desde pausa
                        self._state = "ACTIVO"
                        self._locked_centroid = self._calculate_centroid(closest_hand, fw, fh)
                        self._activation_start_time = None
                        result["active_hand"] = closest_hand
                        result["active_fingers"] = fingers
                        result["handedness"] = self._locked_handedness
                        return result
                else:
                    self._activation_start_time = None
            else:
                self._activation_start_time = None

        return result

    # --- Utilidades ---

    @staticmethod
    def _extract_landmarks(landmarks):
        """Extrae la colección de landmarks tanto si es NormalizedLandmarkList como si es una lista."""
        if landmarks is None:
            return []
        if hasattr(landmarks, "landmark"):
            return landmarks.landmark
        return landmarks

    def _calculate_hand_area(self, landmarks, frame_w, frame_h):
        """Calcula el área aproximada de la caja delimitadora de la mano en píxeles cuadrados."""
        lms = self._extract_landmarks(landmarks)
        xs = [lm.x * frame_w for lm in lms]
        ys = [lm.y * frame_h for lm in lms]
        if not xs or not ys:
            return 0.0
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        return width * height

    def _calculate_centroid(self, landmarks, frame_w, frame_h):
        """Calcula el centroide (x, y) en píxeles de una mano."""
        lms = self._extract_landmarks(landmarks)
        xs = [lm.x * frame_w for lm in lms]
        ys = [lm.y * frame_h for lm in lms]
        if not xs or not ys:
            return (0.0, 0.0)
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    def _find_closest_hand(self, hands, frame_w, frame_h):
        """
        Encuentra la mano más cercana al centroide bloqueado.
        
        Returns:
            tuple: (hand_landmarks, index, distance) o (None, -1, float('inf'))
        """
        if not hands or self._locked_centroid is None:
            return None, -1, float('inf')

        best_hand = None
        best_idx = -1
        best_dist = float('inf')

        for i, hand in enumerate(hands):
            centroid = self._calculate_centroid(hand, frame_w, frame_h)
            dist = math.hypot(
                centroid[0] - self._locked_centroid[0],
                centroid[1] - self._locked_centroid[1]
            )
            if dist < best_dist:
                best_dist = dist
                best_hand = hand
                best_idx = i

        return best_hand, best_idx, best_dist

    @staticmethod
    def _is_palm_open(fingers):
        """Verifica si los dedos representan palma abierta [1,1,1,1,1]."""
        return fingers == [1, 1, 1, 1, 1]

    @staticmethod
    def _is_fist(fingers):
        """Verifica si los dedos representan puño cerrado [0,0,0,0,0]."""
        return fingers == [0, 0, 0, 0, 0]

    def _empty_result(self):
        """Retorna un resultado vacío por defecto."""
        return {
            "state": self._state,
            "active_hand": None,
            "active_fingers": None,
            "handedness": None,
            "activation_progress": self._activation_progress
        }

    # --- Visualización ---

    def draw_lock_status(self, frame, num_hands=0):
        """
        Dibuja indicadores visuales del estado de bloqueo en el frame.
        
        Args:
            frame: Imagen OpenCV (BGR).
            num_hands: Número total de manos detectadas en el frame.
        """
        h, w, _ = frame.shape

        # Panel en la esquina inferior izquierda
        overlay = frame.copy()
        panel_w, panel_h = 265, 60
        panel_x, panel_y = 15, h - panel_h - 15
        cv2.rectangle(overlay, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (60, 60, 60), 1)

        # Color e icono según estado
        state_config = {
            "INACTIVO":  {"color": (100, 100, 100), "icon": "○", "text": "Sin usuario activo"},
            "ACTIVANDO": {"color": (0, 200, 255),   "icon": "◐", "text": "Activando..."},
            "ACTIVO":    {"color": (0, 255, 0),      "icon": "🔒", "text": "Usuario bloqueado"},
            "PERDIDO":   {"color": (0, 180, 255),    "icon": "⚠", "text": "Mano en descanso (Vista)"},
            "PAUSADO":   {"color": (255, 165, 0),    "icon": "⏸", "text": "En pausa"},
        }

        config = state_config.get(self._state, state_config["INACTIVO"])

        # Indicador circular de color
        cx = panel_x + 20
        cy = panel_y + panel_h // 2
        cv2.circle(frame, (cx, cy), 10, config["color"], -1)
        cv2.circle(frame, (cx, cy), 10, (255, 255, 255), 1)

        # Texto del estado y advertencia de intrusos
        if num_hands > 1 and self._state == "ACTIVO":
            cv2.putText(frame, config["text"], (cx + 18, cy - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, config["color"], 1)
            cv2.putText(frame, f"Multi-persona: {num_hands - 1} ignorada(s)", (cx + 18, cy + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 220, 255), 1)
        else:
            cv2.putText(frame, config["text"], (cx + 18, cy + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, config["color"], 1)

        # Barra de progreso durante activación
        if self._state == "ACTIVANDO" and self._activation_progress > 0:
            bar_x = panel_x + 5
            bar_y = panel_y + panel_h - 7
            bar_w = panel_w - 10
            bar_filled = int(bar_w * self._activation_progress)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 4), (60, 60, 60), -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_filled, bar_y + 4), (0, 200, 255), -1)

        # Si hay centroide bloqueado, dibujar cruz en la posición
        if self._locked_centroid and self._state in ("ACTIVO", "PERDIDO"):
            lx, ly = int(self._locked_centroid[0]), int(self._locked_centroid[1])
            cross_color = (0, 255, 0) if self._state == "ACTIVO" else (0, 100, 255)
            cv2.drawMarker(frame, (lx, ly), cross_color, cv2.MARKER_CROSS, 20, 2)

        return frame
