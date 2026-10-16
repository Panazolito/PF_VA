"""
Detector de Parpadeo Intencional para Control de Clics en Modo Ocular.
Proyecto Semestral — Tópicos Especiales I (Visión Artificial) — UTP 2026.

Implementa:
1. Cálculo de EAR (Eye Aspect Ratio) para ojos derecho e izquierdo sin filtrar.
2. Calibración dinámica del EAR base mediante mediana.
3. Histéresis dual (TH_close / TH_open) y compensación por mirada inferior (Y_norm).
4. Filtro Anti-Toque de Midas:
   - Compuerta de velocidad sacádica (px/s).
   - Congelamiento de cursor con buffer deque(maxlen=4).
   - Máquina de estados finita (FSM) por tiempo real (time.perf_counter()).
"""

import time
import math
from collections import deque
import numpy as np
import pyautogui
import cv2


class BlinkDetector:
    """
    Detector de parpadeo intencional para emular clics de ratón mediante seguimiento ocular.
    Totalmente desacoplado de la lógica de captura o seguimiento facial.
    """

    # Índices canónicos de MediaPipe Face Mesh para contorno palpebral
    # Formato: [p1_ext, p2_sup1, p3_sup2, p4_int, p5_inf2, p6_inf1]
    RIGHT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
    LEFT_EYE_INDICES = [362, 385, 387, 263, 373, 380]

    # Estados de la FSM
    STATE_IDLE = "IDLE"
    STATE_CLOSING = "CLOSING"
    STATE_CANCELLED = "CANCELLED"
    STATE_COOLDOWN = "COOLDOWN"

    def __init__(
        self,
        close_factor=0.60,
        open_factor=0.75,
        y_comp_factor=0.20,
        speed_threshold_px_s=750.0,
        min_blink_duration_s=0.35,
        max_blink_duration_s=0.75,
        cancel_duration_s=0.80,
        cooldown_duration_s=0.40,
        calibration_frames=30,
        initial_base_ear=0.30,
        execute_click=True
    ):
        """
        Args:
            close_factor: Proporción del base_ear para detectar cierre (0.60).
            open_factor: Proporción del base_ear para detectar reapertura (0.75).
            y_comp_factor: Atenuación máxima del umbral en mirada inferior (0.20).
            speed_threshold_px_s: Velocidad límite del cursor en px/s para inhibir clics.
            min_blink_duration_s: Tiempo mínimo para considerar parpadeo intencional (0.35 s).
            max_blink_duration_s: Tiempo máximo para validar clic (0.75 s).
            cancel_duration_s: Tiempo de cierre a partir del cual se cancela el clic (0.80 s).
            cooldown_duration_s: Período de enfriamiento tras clic o descarte (0.40 s).
            calibration_frames: Cantidad de cuadros para calibrar la mediana base.
            initial_base_ear: Valor inicial mientras culmina la calibración (0.30).
            execute_click: Si True, llama a pyautogui.click() automáticamente.
        """
        # Asegurar cero retraso en llamadas a pyautogui
        pyautogui.PAUSE = 0

        self.close_factor = close_factor
        self.open_factor = open_factor
        self.y_comp_factor = y_comp_factor
        self.speed_threshold_px_s = speed_threshold_px_s
        self.min_blink_duration_s = min_blink_duration_s
        self.max_blink_duration_s = max_blink_duration_s
        self.cancel_duration_s = cancel_duration_s
        self.cooldown_duration_s = cooldown_duration_s
        self.execute_click = execute_click

        # Calibración dinámica
        self.calibration_frames = calibration_frames
        self.calibration_samples = []
        self.base_ear = float(initial_base_ear)
        self.is_calibrated = False

        # Historial de posiciones suavizadas para congelamiento previo al cierre
        self.cursor_history = deque(maxlen=4)
        self.frozen_cursor_pos = (0, 0)

        # Estimación de velocidad sacádica
        self.prev_cursor_pos = None
        self.prev_time = None
        self.current_speed_px_s = 0.0

        # Máquina de estados
        self.state = self.STATE_IDLE
        self.t_close_start = 0.0
        self.t_cooldown_end = 0.0

    @staticmethod
    def _euclidean_distance(p_a, p_b, frame_w=1.0, frame_h=1.0):
        """Calcula la distancia euclidiana entre dos puntos normalizados o en píxeles."""
        xa = p_a.x if hasattr(p_a, 'x') else (p_a['x'] if isinstance(p_a, dict) else p_a[0])
        ya = p_a.y if hasattr(p_a, 'y') else (p_a['y'] if isinstance(p_a, dict) else p_a[1])
        xb = p_b.x if hasattr(p_b, 'x') else (p_b['x'] if isinstance(p_b, dict) else p_b[0])
        yb = p_b.y if hasattr(p_b, 'y') else (p_b['y'] if isinstance(p_b, dict) else p_b[1])

        dx = (xa - xb) * frame_w
        dy = (ya - yb) * frame_h
        return math.hypot(dx, dy)

    def calculate_single_ear(self, landmarks, indices, frame_w=1.0, frame_h=1.0):
        """
        Calcula el EAR para un conjunto de 6 puntos según la fórmula:
        EAR = (||p2 - p6|| + ||p3 - p5||) / (2 * ||p1 - p4||)
        """
        p1 = landmarks[indices[0]]
        p2 = landmarks[indices[1]]
        p3 = landmarks[indices[2]]
        p4 = landmarks[indices[3]]
        p5 = landmarks[indices[4]]
        p6 = landmarks[indices[5]]

        dist_vertical_1 = self._euclidean_distance(p2, p6, frame_w, frame_h)
        dist_vertical_2 = self._euclidean_distance(p3, p5, frame_w, frame_h)
        dist_horizontal = self._euclidean_distance(p1, p4, frame_w, frame_h)

        if dist_horizontal <= 1e-6:
            return 0.0

        return (dist_vertical_1 + dist_vertical_2) / (2.0 * dist_horizontal)

    def calculate_ear(self, landmarks, frame_w=1.0, frame_h=1.0):
        """Calcula el EAR promedio de ambos ojos sin aplicar filtros One Euro."""
        ear_right = self.calculate_single_ear(landmarks, self.RIGHT_EYE_INDICES, frame_w, frame_h)
        ear_left = self.calculate_single_ear(landmarks, self.LEFT_EYE_INDICES, frame_w, frame_h)
        return (ear_right + ear_left) / 2.0, ear_right, ear_left

    def _update_calibration(self, current_ear):
        """Calibra dinámicamente el base_ear usando la mediana de ojos abiertos."""
        if not self.is_calibrated:
            # Solo acumular si el ojo no está en parpadeo cerrado evidente
            if current_ear > 0.20:
                self.calibration_samples.append(current_ear)
                if len(self.calibration_samples) >= self.calibration_frames:
                    self.base_ear = float(np.median(self.calibration_samples))
                    self.is_calibrated = True

    def reset_calibration(self):
        """Reinicia el proceso de calibración automática."""
        self.calibration_samples.clear()
        self.is_calibrated = False

    def update(self, landmarks, cursor_pos, screen_size, timestamp=None, frame_size=(1.0, 1.0)):
        """
        Actualiza el estado de parpadeo y determina si se permite mover el cursor o ejecutar clic.

        Args:
            landmarks: Lista o contenedor de puntos faciales (mínimo 468 puntos de FaceMesh).
            cursor_pos: Tupla (x, y) de la posición suavizada actual del cursor.
            screen_size: Tupla (screen_width, screen_height).
            timestamp: Marca de tiempo en segundos (time.perf_counter()).
            frame_size: Tupla (frame_w, frame_h) opcional para métrica en píxeles.

        Returns:
            dict con:
                - allow_movement (bool): False si el cursor debe permanecer congelado.
                - target_pos (tuple): Coordenada a usar (congelada si hay cierre, o actual).
                - click_triggered (bool): True en el cuadro exacto donde se valida el clic.
                - ear (float): Valor EAR actual.
                - th_dynamic (float): Umbral dinámico de cierre compensado.
                - th_open (float): Umbral de reapertura.
                - state (str): Estado de la FSM.
                - speed_px_s (float): Velocidad calculada del cursor.
                - blink_duration (float): Duración del parpadeo actual.
        """
        if timestamp is None:
            timestamp = time.perf_counter()

        screen_w, screen_h = screen_size
        frame_w, frame_h = frame_size
        cur_x, cur_y = cursor_pos

        # 1. Medición de velocidad del cursor (px/s)
        if self.prev_cursor_pos is not None and self.prev_time is not None:
            dt = timestamp - self.prev_time
            if dt > 1e-5:
                dx = cur_x - self.prev_cursor_pos[0]
                dy = cur_y - self.prev_cursor_pos[1]
                self.current_speed_px_s = math.hypot(dx, dy) / dt
        else:
            self.current_speed_px_s = 0.0

        self.prev_cursor_pos = (cur_x, cur_y)
        self.prev_time = timestamp

        # 2. Cálculo de EAR bruto
        ear_avg, ear_r, ear_l = self.calculate_ear(landmarks, frame_w, frame_h)
        self._update_calibration(ear_avg)

        # 3. Compensación vertical de mirada
        y_norm = np.clip(cur_y / max(1.0, float(screen_h)), 0.0, 1.0)
        th_close_base = self.close_factor * self.base_ear
        th_dynamic_close = th_close_base * (1.0 - self.y_comp_factor * y_norm)
        th_open = self.open_factor * self.base_ear

        click_triggered = False
        allow_movement = True
        blink_duration = 0.0

        # 4. Máquina de estados en tiempo real
        if self.state == self.STATE_COOLDOWN:
            self.cursor_history.append((cur_x, cur_y))
            if timestamp >= self.t_cooldown_end and ear_avg >= th_open:
                self.state = self.STATE_IDLE
            allow_movement = True
            output_pos = (cur_x, cur_y)

        elif self.state == self.STATE_IDLE:
            # Condición de cierre: EAR por debajo de umbral dinámico Y velocidad no sacádica
            is_saccadic = self.current_speed_px_s > self.speed_threshold_px_s
            if (ear_avg < th_dynamic_close) and not is_saccadic:
                self.state = self.STATE_CLOSING
                self.t_close_start = timestamp
                # Congelar el cursor en la posición previa al inicio del cierre (3 a 4 cuadros antes)
                self.frozen_cursor_pos = self.cursor_history[0] if len(self.cursor_history) > 0 else (cur_x, cur_y)
                allow_movement = False
                output_pos = self.frozen_cursor_pos
            else:
                # Ojo abierto y estable: registrar en el buffer de posiciones
                self.cursor_history.append((cur_x, cur_y))
                allow_movement = True
                output_pos = (cur_x, cur_y)

        elif self.state == self.STATE_CLOSING:
            blink_duration = timestamp - self.t_close_start
            allow_movement = False
            output_pos = self.frozen_cursor_pos

            # Si el ojo permanece cerrado más del límite, cancelar para evitar clics al descansar
            if blink_duration > self.cancel_duration_s:
                self.state = self.STATE_CANCELLED

            # Si el ojo se reabre
            elif ear_avg >= th_open:
                if self.min_blink_duration_s <= blink_duration <= self.max_blink_duration_s:
                    # Parpadeo intencional validado
                    click_triggered = True
                    output_pos = self.frozen_cursor_pos
                    if self.execute_click:
                        pyautogui.click(x=int(self.frozen_cursor_pos[0]), y=int(self.frozen_cursor_pos[1]))
                    self.state = self.STATE_COOLDOWN
                    self.t_cooldown_end = timestamp + self.cooldown_duration_s
                else:
                    # Parpadeo involuntario (<0.30s) o fuera de rango: descartar
                    self.state = self.STATE_IDLE
                    output_pos = (cur_x, cur_y)
                allow_movement = True

        elif self.state == self.STATE_CANCELLED:
            allow_movement = True
            output_pos = (cur_x, cur_y)
            # Esperar a que el usuario reabra los ojos completamente para reiniciar
            if ear_avg >= th_open:
                self.state = self.STATE_COOLDOWN
                self.t_cooldown_end = timestamp + self.cooldown_duration_s

        else:
            self.state = self.STATE_IDLE
            output_pos = (cur_x, cur_y)

        return {
            "allow_movement": allow_movement,
            "target_pos": output_pos,
            "click_triggered": click_triggered,
            "ear": ear_avg,
            "ear_right": ear_r,
            "ear_left": ear_l,
            "th_dynamic": th_dynamic_close,
            "th_open": th_open,
            "base_ear": self.base_ear,
            "state": self.state,
            "speed_px_s": self.current_speed_px_s,
            "blink_duration": blink_duration,
            "is_calibrated": self.is_calibrated
        }

    def draw_hud(self, frame, blink_res, x=15, y=200):
        """
        Dibuja un panel de telemetría de parpadeo en el frame de OpenCV.
        """
        overlay = frame.copy()
        panel_w, panel_h = 295, 115
        cv2.rectangle(overlay, (x, y), (x + panel_w, y + panel_h), (25, 25, 25), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
        cv2.rectangle(frame, (x, y), (x + panel_w, y + panel_h), (80, 80, 80), 1)

        state = blink_res["state"]
        ear = blink_res["ear"]
        th_close = blink_res["th_dynamic"]
        duration = blink_res["blink_duration"]

        color_state = (0, 255, 128) if state == self.STATE_IDLE else (
            (0, 215, 255) if state == self.STATE_CLOSING else (
                (0, 0, 255) if state == self.STATE_CANCELLED else (255, 165, 0)
            )
        )

        cv2.putText(frame, f"Modo Ocular: Parpadeo", (x + 10, y + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)
        cv2.putText(frame, f"Estado: {state}", (x + 10, y + 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color_state, 1)

        # Barra indicadora de EAR vs Umbral
        ear_text = f"EAR: {ear:.3f} | Umbral: {th_close:.3f}"
        cv2.putText(frame, ear_text, (x + 10, y + 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)

        dur_text = f"Duracion: {duration:.2f}s (0.35-0.75s)"
        cv2.putText(frame, dur_text, (x + 10, y + 92),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1)

        if blink_res["click_triggered"]:
            cv2.circle(frame, (x + panel_w - 30, y + 30), 12, (0, 255, 0), -1)
            cv2.putText(frame, "CLIC", (x + panel_w - 55, y + 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 0), 1)

        return frame
