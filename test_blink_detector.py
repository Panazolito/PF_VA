"""
Pruebas Unitarias para el Módulo BlinkDetector (Detección de Parpadeo Intencional).
Verifica:
1. Cálculo de EAR geométrico para ojo derecho e izquierdo.
2. Calibración dinámica del EAR base mediante mediana.
3. Histéresis dual y compensación de mirada inferior (Y_norm).
4. Compuerta de velocidad sacádica (px/s).
5. Congelamiento del cursor en posición pre-cierre (deque maxlen=4).
6. Máquina de estados finita por tiempo real (<0.30s, 0.35-0.75s, >0.80s).
7. Configuración de pyautogui.PAUSE = 0.
"""

import unittest
from unittest.mock import patch, MagicMock
import pyautogui
from blink_detector import BlinkDetector


class FakeLandmark:
    """Simula un punto de MediaPipe con atributos x, y, z."""
    def __init__(self, x, y, z=0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


def create_synthetic_face_mesh(eye_open_ratio=0.35):
    """
    Crea una lista de 478 landmarks sintéticos con apertura ocular controlada.
    """
    landmarks = [FakeLandmark(0.5, 0.5) for _ in range(478)]

    # Ancho horizontal del ojo: 0.10
    # Ojo Derecho: [33, 160, 158, 133, 153, 144]
    # p1=33, p4=133
    landmarks[33] = FakeLandmark(0.30, 0.40)
    landmarks[133] = FakeLandmark(0.40, 0.40)
    h_dist = 0.10
    v_dist = eye_open_ratio * h_dist

    # Párpados superiores
    landmarks[160] = FakeLandmark(0.33, 0.40 - v_dist / 2.0)
    landmarks[158] = FakeLandmark(0.37, 0.40 - v_dist / 2.0)
    # Párpados inferiores
    landmarks[144] = FakeLandmark(0.33, 0.40 + v_dist / 2.0)
    landmarks[153] = FakeLandmark(0.37, 0.40 + v_dist / 2.0)

    # Ojo Izquierdo: [362, 385, 387, 263, 373, 380]
    # p1=362, p4=263
    landmarks[362] = FakeLandmark(0.60, 0.40)
    landmarks[263] = FakeLandmark(0.70, 0.40)
    # Párpados superiores
    landmarks[385] = FakeLandmark(0.63, 0.40 - v_dist / 2.0)
    landmarks[387] = FakeLandmark(0.67, 0.40 - v_dist / 2.0)
    # Párpados inferiores
    landmarks[380] = FakeLandmark(0.63, 0.40 + v_dist / 2.0)
    landmarks[373] = FakeLandmark(0.67, 0.40 + v_dist / 2.0)

    return landmarks


class TestBlinkDetector(unittest.TestCase):

    def setUp(self):
        self.detector = BlinkDetector(
            close_factor=0.60,
            open_factor=0.75,
            y_comp_factor=0.20,
            speed_threshold_px_s=750.0,
            min_blink_duration_s=0.35,
            max_blink_duration_s=0.75,
            cancel_duration_s=0.80,
            cooldown_duration_s=0.40,
            initial_base_ear=0.30,
            execute_click=False
        )

    def test_pyautogui_pause_is_zero(self):
        """Verifica que pyautogui.PAUSE esté fijado en 0."""
        self.assertEqual(pyautogui.PAUSE, 0)

    def test_ear_calculation_open_and_closed(self):
        """Verifica la fórmula euclidiana del EAR para ojos abiertos y cerrados."""
        open_face = create_synthetic_face_mesh(eye_open_ratio=0.32)
        ear_open, ear_r, ear_l = self.detector.calculate_ear(open_face)
        self.assertAlmostEqual(ear_open, 0.32, delta=0.01)

        closed_face = create_synthetic_face_mesh(eye_open_ratio=0.05)
        ear_closed, _, _ = self.detector.calculate_ear(closed_face)
        self.assertAlmostEqual(ear_closed, 0.05, delta=0.01)
        self.assertLess(ear_closed, ear_open)

    def test_vertical_compensation_threshold(self):
        """
        Verifica que al mirar hacia abajo (Y_norm = 1.0) el umbral de cierre
        se reduzca en un 20% para evitar falsos positivos.
        """
        open_face = create_synthetic_face_mesh(0.30)
        screen_size = (1920, 1080)

        # Mirando arriba (Y = 0)
        res_top = self.detector.update(open_face, (500, 0), screen_size, timestamp=1.0)
        th_top = res_top["th_dynamic"]
        expected_top = 0.60 * self.detector.base_ear
        self.assertAlmostEqual(th_top, expected_top, places=4)

        # Mirando abajo (Y = 1080 -> Y_norm = 1.0)
        res_bottom = self.detector.update(open_face, (500, 1080), screen_size, timestamp=1.1)
        th_bottom = res_bottom["th_dynamic"]
        expected_bottom = (0.60 * self.detector.base_ear) * 0.80  # 1 - 0.20*1.0
        self.assertAlmostEqual(th_bottom, expected_bottom, places=4)
        self.assertLess(th_bottom, th_top)

    def test_speed_gate_blocks_saccade(self):
        """
        Verifica que una velocidad del cursor mayor a 750 px/s bloquee
        el inicio del parpadeo (movimiento sacádico).
        """
        open_face = create_synthetic_face_mesh(0.30)
        closed_face = create_synthetic_face_mesh(0.05)
        screen_size = (1920, 1080)

        # Frame 1 en reposo
        self.detector.update(open_face, (100, 100), screen_size, timestamp=1.0)

        # Frame 2: Salto sacádico rápido (de 100 a 300 px en 0.02s -> 10000 px/s)
        # Ojo se cierra simultáneamente
        res = self.detector.update(closed_face, (300, 100), screen_size, timestamp=1.02)

        # La compuerta debe impedir el paso a CLOSING debido a la alta velocidad
        self.assertEqual(res["state"], BlinkDetector.STATE_IDLE)
        self.assertTrue(res["allow_movement"])

    def test_cursor_freeze_on_closure(self):
        """
        Verifica que cuando inicia el cierre palpebral, el cursor se congele
        en la posición previa (3-4 cuadros antes en deque(maxlen=4)).
        """
        open_face = create_synthetic_face_mesh(0.30)
        closed_face = create_synthetic_face_mesh(0.05)
        screen_size = (1920, 1080)

        # Llenar historial en reposo (velocidad baja)
        t = 1.0
        self.detector.update(open_face, (100, 200), screen_size, timestamp=t); t += 0.05
        self.detector.update(open_face, (102, 201), screen_size, timestamp=t); t += 0.05
        self.detector.update(open_face, (104, 202), screen_size, timestamp=t); t += 0.05
        self.detector.update(open_face, (106, 203), screen_size, timestamp=t); t += 0.05

        # Ojo se cierra en posición desplazada (ej. salto de iris a (115, 220))
        res = self.detector.update(closed_face, (115, 220), screen_size, timestamp=t)

        self.assertEqual(res["state"], BlinkDetector.STATE_CLOSING)
        self.assertFalse(res["allow_movement"])
        # La coordenada congelada debe coincidir con el primer elemento de la deque previa
        self.assertEqual(res["target_pos"], (100, 200))

    def test_involuntary_blink_ignored(self):
        """
        Verifica que un parpadeo menor a 0.30 s sea ignorado (sin clic).
        """
        open_face = create_synthetic_face_mesh(0.30)
        closed_face = create_synthetic_face_mesh(0.05)
        screen_size = (1920, 1080)

        # Inicia cierre en t = 1.0
        self.detector.update(closed_face, (500, 500), screen_size, timestamp=1.0)
        # Permanece cerrado 0.15 s
        self.detector.update(closed_face, (500, 500), screen_size, timestamp=1.15)
        # Se reabre a los 0.20 s (< 0.30 s)
        res = self.detector.update(open_face, (500, 500), screen_size, timestamp=1.20)

        self.assertFalse(res["click_triggered"])
        self.assertEqual(res["state"], BlinkDetector.STATE_IDLE)
        self.assertTrue(res["allow_movement"])

    def test_intentional_blink_triggers_click(self):
        """
        Verifica que un parpadeo intencional entre 0.35 s y 0.75 s dispare el clic
        y entre en cooldown.
        """
        open_face = create_synthetic_face_mesh(0.30)
        closed_face = create_synthetic_face_mesh(0.05)
        screen_size = (1920, 1080)

        # Historial estable
        self.detector.update(open_face, (400, 400), screen_size, timestamp=1.0)
        self.detector.update(open_face, (400, 400), screen_size, timestamp=1.03)

        # Inicia cierre en t = 2.0
        self.detector.update(closed_face, (405, 405), screen_size, timestamp=2.0)
        # Ojo sigue cerrado durante 0.50 s
        self.detector.update(closed_face, (410, 410), screen_size, timestamp=2.50)
        # Reapertura en t = 2.52 s (duración = 0.52 s, dentro de [0.35, 0.75])
        res = self.detector.update(open_face, (410, 410), screen_size, timestamp=2.52)

        self.assertTrue(res["click_triggered"])
        self.assertEqual(res["target_pos"], (400, 400))
        self.assertEqual(res["state"], BlinkDetector.STATE_COOLDOWN)

    def test_long_closure_cancels_click(self):
        """
        Verifica que un cierre prolongado (> 0.80 s, descanso ocular)
        cancele el clic.
        """
        open_face = create_synthetic_face_mesh(0.30)
        closed_face = create_synthetic_face_mesh(0.05)
        screen_size = (1920, 1080)

        # Inicia cierre en t = 1.0
        self.detector.update(closed_face, (500, 500), screen_size, timestamp=1.0)
        # Transcurren 0.90 s cerrado
        res_closed = self.detector.update(closed_face, (500, 500), screen_size, timestamp=1.90)
        self.assertEqual(res_closed["state"], BlinkDetector.STATE_CANCELLED)

        # Se reabre el ojo
        res_open = self.detector.update(open_face, (500, 500), screen_size, timestamp=2.0)
        self.assertFalse(res_open["click_triggered"])


class TestComputeGazeScreenPos(unittest.TestCase):
    """Verifica el mapeo de iris a coordenadas de pantalla y protección anti-FailSafe."""

    def test_centered_iris_maps_to_screen_center(self):
        from gesture_controller import OneEuroFilter2D
        from main_ocular import compute_gaze_screen_pos

        landmarks = create_synthetic_face_mesh(0.35)
        landmarks[468] = FakeLandmark(0.5, 0.5)
        landmarks[473] = FakeLandmark(0.5, 0.5)
        filt = OneEuroFilter2D(min_cutoff=1.2, beta=0.015)

        sx, sy, _ = compute_gaze_screen_pos(landmarks, 1920, 1080, filt, timestamp=1.0)
        self.assertEqual((sx, sy), (960, 540))

    def test_compute_gaze_clamps_corners(self):
        """Evita (0, 0) y el borde extremo para no disparar FailSafeException de PyAutoGUI."""
        from gesture_controller import OneEuroFilter2D
        from main_ocular import compute_gaze_screen_pos

        landmarks = create_synthetic_face_mesh(0.35)
        landmarks[468] = FakeLandmark(0.0, 0.0)
        landmarks[473] = FakeLandmark(0.0, 0.0)
        filt = OneEuroFilter2D(min_cutoff=1.2, beta=0.015)

        sx, sy, _ = compute_gaze_screen_pos(landmarks, 1920, 1080, filt, timestamp=1.0)
        self.assertEqual((sx, sy), (1, 1))


if __name__ == "__main__":
    unittest.main()

