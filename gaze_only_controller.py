"""
Controlador y Bucle para el Modo "Solo Mirada" (100% Ocular y Gestos Faciales).
Proyecto Semestral — Tópicos Especiales I (Visión Artificial) — UTP 2026.

Controles del Modo "Solo Mirada":
- Mover el cursor          → Mirada (Iris 468 y 473 con Filtro One Euro)
- Activar control          → Dejar ambos ojos cerrados por 2.0 s
- Pausar control           → Sonreír por 2.0 s
- Clic izquierdo           → Guiñar ojo izquierdo
- Clic derecho             → Guiñar ojo derecho
- Modo SCROLL              → Sacar la lengua (y mirar arriba/abajo para desplazar)
"""

import math
import time
from collections import deque
import cv2
import numpy as np
import pyautogui


class GazeOnlyController:
    """
    Máquina de estados y detector multimodal facial (Face Mesh) para operar el sistema
    únicamente con la mirada y gestos faciales.
    """

    #En imagen espejada (cv2.flip(frame, 1)):
    # Lado izquierdo de la imagen (x menor) = Ojo izquierdo físico del usuario
    USER_LEFT_EYE = [33, 160, 158, 133, 153, 144]
    # Lado derecho de la imagen (x mayor) = Ojo derecho físico del usuario
    USER_RIGHT_EYE = [362, 385, 387, 263, 373, 380]

    # Puntos labiales de MediaPipe Face Mesh
    UPPER_INNER_LIP = 13
    LOWER_INNER_LIP = 14
    MOUTH_LEFT_CORNER = 61
    MOUTH_RIGHT_CORNER = 291
    UPPER_OUTER_LIP = 0
    LOWER_OUTER_LIP = 17

    def __init__(
        self,
        screen_width,
        screen_height,
        execute_actions=True,
        activation_close_time_s=2.0,
        reactivation_close_time_s=2.0,
        smile_pause_time_s=2.0,
        wink_hold_time_s=0.16,
        wink_cooldown_s=0.45,
        calibration_frames=25
    ):
        pyautogui.PAUSE = 0
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.execute_actions = execute_actions

        self.activation_close_time_s = activation_close_time_s
        self.reactivation_close_time_s = reactivation_close_time_s
        self.smile_pause_time_s = smile_pause_time_s
        self.wink_hold_time_s = wink_hold_time_s
        self.wink_cooldown_s = wink_cooldown_s
        self.calibration_frames = calibration_frames

        # Estado de sesión: INACTIVO, ACTIVANDO, ACTIVO, PAUSADO
        self.state = "INACTIVO"
        self.progress = 0.0
        self.pause_progress = 0.0

        # Calibración facial adaptativa (EAR basal de cada ojo y ancho neutral de boca)
        self.is_calibrated = False
        self._cal_left_ear = []
        self._cal_right_ear = []
        self._cal_mouth_ratio = []
        self.base_ear_left = 0.29
        self.base_ear_right = 0.29
        self.base_mouth_ratio = 0.50

        # Temporizadores de gestos
        self._both_closed_start = None
        self._smile_start = None
        self._left_wink_start = None
        self._right_wink_start = None
        self._left_wink_fired = False
        self._right_wink_fired = False
        self._last_click_time = 0.0

        # Historial de posiciones oculares para congelar el cursor antes de un guiño/parpadeo
        self.cursor_history = deque(maxlen=6)
        self.frozen_cursor_pos = None

    def reset_calibration(self):
        """Reinicia la calibración basal de ojos y boca."""
        self.is_calibrated = False
        self._cal_left_ear.clear()
        self._cal_right_ear.clear()
        self._cal_mouth_ratio.clear()

    @staticmethod
    def _dist(p1, p2, fw=1.0, fh=1.0):
        return math.hypot((p1.x - p2.x) * fw, (p1.y - p2.y) * fh)

    def _compute_eye_ear(self, landmarks, indices, fw=1.0, fh=1.0):
        p1, p2, p3, p4, p5, p6 = [landmarks[i] for i in indices]
        v1 = self._dist(p2, p6, fw, fh)
        v2 = self._dist(p3, p5, fw, fh)
        h = self._dist(p1, p4, fw, fh)
        if h <= 1e-6:
            return 0.0
        return (v1 + v2) / (2.0 * h)

    def _compute_mouth_metrics(self, landmarks, fw=1.0, fh=1.0):
        """
        Calcula métricas geométricas de la boca:
        - mar (Mouth Aspect Ratio): apertura vertical interna / ancho de boca
        - mouth_width_ratio: ancho de boca / distancia inter-ocular externa
        - corner_lift: elevación de las comisuras respecto al centro labial
        """
        p_up = landmarks[self.UPPER_INNER_LIP]
        p_lo = landmarks[self.LOWER_INNER_LIP]
        p_left = landmarks[self.MOUTH_LEFT_CORNER]
        p_right = landmarks[self.MOUTH_RIGHT_CORNER]
        p_eye_l = landmarks[33]
        p_eye_r = landmarks[263]

        vertical_open = self._dist(p_up, p_lo, fw, fh)
        mouth_width = max(1e-5, self._dist(p_left, p_right, fw, fh))
        eye_span = max(1e-5, self._dist(p_eye_l, p_eye_r, fw, fh))

        mar = vertical_open / mouth_width
        mouth_width_ratio = mouth_width / eye_span

        # En OpenCV, y menor = más arriba. Si las comisuras suben respecto al centro de los labios, es sonrisa
        center_lip_y = (p_up.y + p_lo.y) * 0.5
        corners_y = (p_left.y + p_right.y) * 0.5
        corner_lift = (center_lip_y - corners_y) / max(1e-5, eye_span / max(1.0, fw))

        return mar, mouth_width_ratio, corner_lift

    def _update_calibration(self, ear_l, ear_r, mar, mouth_ratio):
        if self.is_calibrated:
            return
        # Calibrar solo cuando los ojos están abiertos y la boca está en postura neutral
        if ear_l > 0.19 and ear_r > 0.19 and mar < 0.20:
            self._cal_left_ear.append(ear_l)
            self._cal_right_ear.append(ear_r)
            self._cal_mouth_ratio.append(mouth_ratio)
            if len(self._cal_left_ear) >= self.calibration_frames:
                self.base_ear_left = float(np.median(self._cal_left_ear))
                self.base_ear_right = float(np.median(self._cal_right_ear))
                self.base_mouth_ratio = float(np.median(self._cal_mouth_ratio))
                self.is_calibrated = True

    def update(self, landmarks, gaze_pos, frame_w, frame_h, now=None):
        """
        Procesa los landmarks faciales y ejecuta las acciones del Modo Solo Mirada.
        """
        if now is None:
            now = time.perf_counter()

        result = {
            "state": self.state,
            "mode": "REPOSO",
            "gesture_name": "Mirada activa",
            "allow_movement": True,
            "cursor_locked": False,
            "left_clicked": False,
            "right_clicked": False,
            "scrolled": False,
            "scroll_amount": 0,
            "activation_progress": 0.0,
            "pause_progress": 0.0,
            "ear_left": 0.0,
            "ear_right": 0.0,
            "mar": 0.0,
            "is_calibrated": self.is_calibrated,
        }

        if landmarks is None or gaze_pos is None:
            self._both_closed_start = None
            self._smile_start = None
            self._left_wink_start = None
            self._right_wink_start = None
            self.frozen_cursor_pos = None
            return result

        gx, gy = int(gaze_pos[0]), int(gaze_pos[1])

        ear_l = self._compute_eye_ear(landmarks, self.USER_LEFT_EYE, frame_w, frame_h)
        ear_r = self._compute_eye_ear(landmarks, self.USER_RIGHT_EYE, frame_w, frame_h)
        mar, mouth_ratio, corner_lift = self._compute_mouth_metrics(landmarks, frame_w, frame_h)

        self._update_calibration(ear_l, ear_r, mar, mouth_ratio)

        result["ear_left"] = ear_l
        result["ear_right"] = ear_r
        result["mar"] = mar
        result["is_calibrated"] = self.is_calibrated

        # Compensación suave cuando el usuario mira hacia la parte baja de la pantalla
        y_norm = np.clip(gy / max(1.0, float(self.screen_height)), 0.0, 1.0)
        comp = 1.0 - 0.16 * y_norm

        th_close_l = self.base_ear_left * 0.62 * comp
        th_open_l = self.base_ear_left * 0.72 * comp
        th_close_r = self.base_ear_right * 0.62 * comp
        th_open_r = self.base_ear_right * 0.72 * comp

        left_closed = ear_l < th_close_l
        right_closed = ear_r < th_close_r
        left_clearly_open = ear_l >= th_open_l
        right_clearly_open = ear_r >= th_open_r

        # 1. Detección de AMBOS ojos cerrados (Activar / Reactivar control por 2s)
        both_eyes_closed = (ear_l < self.base_ear_left * 0.66 * comp) and (ear_r < self.base_ear_right * 0.66 * comp)

        # 2. Detección de Guiño Izquierdo vs Guiño Derecho (un ojo cerrado y el otro abierto con asimetría clara)
        is_left_wink = left_closed and right_clearly_open and ((ear_r - ear_l) > 0.045)
        is_right_wink = right_closed and left_clearly_open and ((ear_l - ear_r) > 0.045)

        # 3. Detección de Sacar la Lengua (apertura vertical alta de la boca)
        is_tongue_out = mar >= 0.21

        # 4. Detección de Sonrisa (comisuras estiradas horizontalmente o elevadas, sin abrir exageradamente la boca)
        smile_threshold = max(self.base_mouth_ratio * 1.11, self.base_mouth_ratio + 0.045)
        is_smiling = (not is_tongue_out) and (
            (mouth_ratio >= smile_threshold) or (mouth_ratio >= self.base_mouth_ratio * 1.06 and corner_lift > 0.018)
        )

        # Congelar el cursor si cualquier ojo está cerrándose para evitar saltos del iris
        any_eye_closing = (ear_l < th_open_l) or (ear_r < th_open_r)
        if not any_eye_closing:
            self.cursor_history.append((gx, gy))
            self.frozen_cursor_pos = None
        else:
            if self.frozen_cursor_pos is None:
                self.frozen_cursor_pos = self.cursor_history[0] if len(self.cursor_history) > 0 else (gx, gy)

        active_cursor_x, active_cursor_y = self.frozen_cursor_pos if self.frozen_cursor_pos is not None else (gx, gy)

        # =====================================================================
        # MÁQUINA DE ESTADOS DE SESIÓN (INACTIVO / ACTIVANDO / PAUSADO / ACTIVO)
        # =====================================================================
        if self.state in ("INACTIVO", "ACTIVANDO", "PAUSADO"):
            result["allow_movement"] = False
            req_time = self.activation_close_time_s if self.state != "PAUSADO" else self.reactivation_close_time_s

            if both_eyes_closed:
                if self._both_closed_start is None:
                    self._both_closed_start = now
                elapsed = now - self._both_closed_start
                prog = min(1.0, elapsed / req_time)
                result["activation_progress"] = prog
                if self.state == "INACTIVO":
                    self.state = "ACTIVANDO"
                result["gesture_name"] = f"Ojos cerrados ({elapsed:.1f}s / {req_time:.0f}s)"

                if elapsed >= req_time:
                    self.state = "ACTIVO"
                    self._both_closed_start = None
                    self._smile_start = None
                    result["activation_progress"] = 1.0
                    result["gesture_name"] = "¡Control Activado!"
            else:
                self._both_closed_start = None
                if self.state == "ACTIVANDO":
                    self.state = "INACTIVO"
                result["gesture_name"] = (
                    "Cierra ambos ojos 2s para activar"
                    if self.state == "INACTIVO"
                    else "En pausa (Cierra ambos ojos 2s para reanudar)"
                )

            result["state"] = self.state
            return result

        # =====================================================================
        # ESTADO ACTIVO: PROCESAR PAUSA (SONRISA 2s), SCROLL (LENGUA) Y CLICS (GUIÑOS)
        # =====================================================================
        result["state"] = "ACTIVO"

        # A. Verificar gesto de Pausa: Sonreír por 2s
        if is_smiling and not any_eye_closing:
            if self._smile_start is None:
                self._smile_start = now
            smile_elapsed = now - self._smile_start
            result["pause_progress"] = min(1.0, smile_elapsed / self.smile_pause_time_s)
            result["gesture_name"] = f"Sonriendo — Pausando ({smile_elapsed:.1f}s / 2s)"
            result["mode"] = "PAUSANDO"
            if smile_elapsed >= self.smile_pause_time_s:
                self.state = "PAUSADO"
                result["state"] = "PAUSADO"
                self._smile_start = None
                result["allow_movement"] = False
                return result
        else:
            self._smile_start = None

        # B. Verificar Modo SCROLL: Sacar la lengua
        if is_tongue_out and not both_eyes_closed:
            self._left_wink_start = None
            self._right_wink_start = None
            result["mode"] = "SCROLL"
            result["cursor_locked"] = True
            result["allow_movement"] = False

            center_y = self.screen_height / 2.0
            deadzone_y = self.screen_height * 0.12
            scroll_amount = 0

            if gy < center_y - deadzone_y:
                span = max(1.0, center_y - deadzone_y)
                norm_offset = min(1.0, (center_y - deadzone_y - gy) / span)
                scroll_amount = int(round(20 + 70 * norm_offset))
                result["gesture_name"] = "Lengua afuera → Scroll Arriba ^"
            elif gy > center_y + deadzone_y:
                span = max(1.0, self.screen_height - (center_y + deadzone_y))
                norm_offset = min(1.0, (gy - (center_y + deadzone_y)) / span)
                scroll_amount = -int(round(20 + 70 * norm_offset))
                result["gesture_name"] = "Lengua afuera → Scroll Abajo v"
            else:
                result["gesture_name"] = "Lengua afuera → Modo SCROLL (Mira arriba/abajo)"

            if scroll_amount != 0:
                result["scrolled"] = True
                result["scroll_amount"] = scroll_amount
                if self.execute_actions:
                    pyautogui.scroll(scroll_amount)

            return result

        # C. Verificar Guiño Izquierdo → Clic Izquierdo
        if is_left_wink:
            self._right_wink_start = None
            result["mode"] = "PUNTERO"
            result["cursor_locked"] = True
            result["allow_movement"] = False
            result["gesture_name"] = "Guiño ojo izquierdo"

            if self._left_wink_start is None:
                self._left_wink_start = now
                self._left_wink_fired = False
            elif (
                not self._left_wink_fired
                and (now - self._left_wink_start) >= self.wink_hold_time_s
                and (now - self._last_click_time) >= self.wink_cooldown_s
            ):
                self._left_wink_fired = True
                self._last_click_time = now
                result["left_clicked"] = True
                result["gesture_name"] = "¡Clic Izquierdo! (Guiño Izq)"
                if self.execute_actions:
                    pyautogui.click(x=active_cursor_x, y=active_cursor_y)
            return result
        else:
            self._left_wink_start = None
            self._left_wink_fired = False

        # D. Verificar Guiño Derecho → Clic Derecho
        if is_right_wink:
            self._left_wink_start = None
            result["mode"] = "CLIC_DERECHO"
            result["cursor_locked"] = True
            result["allow_movement"] = False
            result["gesture_name"] = "Guiño ojo derecho"

            if self._right_wink_start is None:
                self._right_wink_start = now
                self._right_wink_fired = False
            elif (
                not self._right_wink_fired
                and (now - self._right_wink_start) >= self.wink_hold_time_s
                and (now - self._last_click_time) >= self.wink_cooldown_s
            ):
                self._right_wink_fired = True
                self._last_click_time = now
                result["right_clicked"] = True
                result["gesture_name"] = "¡Clic Derecho! (Guiño Der)"
                if self.execute_actions:
                    pyautogui.rightClick(x=active_cursor_x, y=active_cursor_y)
            return result
        else:
            self._right_wink_start = None
            self._right_wink_fired = False

        # E. Si ambos ojos están cerrándose (parpadeo natural), congelar el cursor sin disparar clic
        if any_eye_closing:
            result["mode"] = "PUNTERO"
            result["cursor_locked"] = True
            result["allow_movement"] = False
            result["gesture_name"] = "Parpadeo (Cursor fijado)"
            return result

        # F. Navegación ocular normal
        result["mode"] = "PUNTERO"
        result["allow_movement"] = True
        result["cursor_locked"] = False
        if not is_smiling:
            result["gesture_name"] = "Mirada activa (Puntero)"
        return result

    def draw_hud(self, frame, res, fps, sensitivity):
        """Dibuja el panel HUD superior e inferior para el Modo Solo Mirada."""
        h, w, _ = frame.shape

        # Panel superior
        overlay = frame.copy()
        panel_w, panel_h = 345, 135
        cv2.rectangle(overlay, (15, 15), (15 + panel_w, 15 + panel_h), (20, 20, 22), -1)
        cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
        cv2.rectangle(frame, (15, 15), (15 + panel_w, 15 + panel_h), (90, 90, 95), 1)

        cv2.putText(frame, f"FPS: {int(fps)}", (25, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 128), 2)
        cv2.putText(frame, "Modo: SOLO MIRADA", (110, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (230, 230, 230), 1)
        cv2.putText(frame, f"Sens: {sensitivity:.1f}x", (265, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 255), 1)

        cv2.line(frame, (25, 50), (15 + panel_w - 10, 50), (65, 65, 70), 1)

        cv2.putText(
            frame,
            f"Accion: {res['gesture_name']}",
            (25, 76),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (255, 255, 255),
            1
        )

        ear_txt = f"Ojo Izq: {res['ear_left']:.2f} | Ojo Der: {res['ear_right']:.2f} | Boca: {res['mar']:.2f}"
        cv2.putText(frame, ear_txt, (25, 102), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (190, 190, 200), 1)

        cal_txt = "Calibrado (Tecla 'r' recalibrar)" if res["is_calibrated"] else "Calibrando rostro..."
        cal_col = (120, 255, 140) if res["is_calibrated"] else (0, 215, 255)
        cv2.putText(frame, cal_txt, (25, 128), cv2.FONT_HERSHEY_SIMPLEX, 0.38, cal_col, 1)

        # Panel inferior de estado (igual estilo que UserLock)
        overlay2 = frame.copy()
        b_w, b_h = 305, 60
        bx, by = 15, h - b_h - 15
        cv2.rectangle(overlay2, (bx, by), (bx + b_w, by + b_h), (20, 20, 22), -1)
        cv2.addWeighted(overlay2, 0.78, frame, 0.22, 0, frame)
        cv2.rectangle(frame, (bx, by), (bx + b_w, by + b_h), (70, 70, 75), 1)

        state = res["state"]
        state_cfg = {
            "INACTIVO":  {"color": (130, 130, 130), "text": "Inactivo (Cierra ojos 2s)"},
            "ACTIVANDO": {"color": (0, 200, 255),   "text": "Activando (Ojos cerrados)..."},
            "ACTIVO":    {"color": (0, 255, 0),     "text": "Control Ocular ACTIVO"},
            "PAUSADO":   {"color": (255, 165, 0),   "text": "En pausa (Cierra ojos 2s)"},
        }
        cfg = state_cfg.get(state, state_cfg["INACTIVO"])

        cx, cy = bx + 20, by + b_h // 2
        cv2.circle(frame, (cx, cy), 10, cfg["color"], -1)
        cv2.circle(frame, (cx, cy), 10, (255, 255, 255), 1)
        cv2.putText(frame, cfg["text"], (cx + 18, cy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.46, cfg["color"], 1)

        # Barra de progreso de activación o pausa
        prog = res["activation_progress"] if state in ("INACTIVO", "ACTIVANDO", "PAUSADO") else res["pause_progress"]
        if prog > 0:
            bar_x = bx + 6
            bar_y = by + b_h - 8
            bar_w = b_w - 12
            bar_fill = int(bar_w * prog)
            bar_col = (0, 200, 255) if state != "ACTIVO" else (255, 165, 0)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 4), (60, 60, 60), -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_fill, bar_y + 4), bar_col, -1)

        return frame
