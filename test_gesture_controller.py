"""
Tests para el módulo gesture_controller.py
Valida suavizado de cursor, debounce de clics, modos gestuales y acciones.
"""
import unittest
import time


class TestCursorSmoother(unittest.TestCase):
    """Pruebas para el filtro de suavizado exponencial del cursor."""

    def setUp(self):
        from gesture_controller import CursorSmoother
        self.smoother = CursorSmoother(smoothing_factor=0.5)

    def test_first_position_jumps_directly(self):
        """La primera posición no debe suavizarse — ir directo."""
        x, y = self.smoother.smooth(500, 300)
        self.assertEqual(x, 500)
        self.assertEqual(y, 300)

    def test_smoothing_reduces_jump(self):
        """Un salto grande debe reducirse por el filtro EMA."""
        self.smoother.smooth(100, 100)
        x, y = self.smoother.smooth(500, 500)
        # Con factor 0.5: new = old + (target - old) * 0.5
        # x = 100 + (500 - 100) * 0.5 = 300
        self.assertEqual(x, 300)
        self.assertEqual(y, 300)

    def test_repeated_same_position_converges(self):
        """Enviar la misma posición repetidamente debe converger a ella."""
        self.smoother.smooth(0, 0)
        for _ in range(20):
            x, y = self.smoother.smooth(1000, 1000)
        # Después de 20 iteraciones con factor 0.5, debe estar muy cerca de 1000
        self.assertAlmostEqual(x, 1000, delta=1)
        self.assertAlmostEqual(y, 1000, delta=1)

    def test_deadzone_anti_tremor(self):
        """Verifica que micro-temblores menores al deadzone no muevan el cursor."""
        from gesture_controller import CursorSmoother
        smoother = CursorSmoother(smoothing_factor=0.5, deadzone_px=5)
        # Fijar posición inicial
        smoother.smooth(500, 500)
        # Movimiento diminuto (temblor de mano de 2 px < 5 px)
        x, y = smoother.smooth(502, 501)
        self.assertEqual(x, 500)
        self.assertEqual(y, 500)
        # Movimiento intencional grande (> 5 px)
        x2, y2 = smoother.smooth(530, 530)
        self.assertNotEqual(x2, 500)
        self.assertNotEqual(y2, 500)


class TestClickDebouncer(unittest.TestCase):
    """Pruebas para el sistema de debounce y cooldown de clics."""

    def setUp(self):
        from gesture_controller import ClickDebouncer
        self.debouncer = ClickDebouncer(
            hold_time_ms=150,
            cooldown_ms=300
        )

    def test_instant_pinch_does_not_click(self):
        """Un pellizco instantáneo (1 frame) no debe disparar clic."""
        result = self.debouncer.update(is_pinching=True)
        self.assertFalse(result)

    def test_sustained_pinch_clicks(self):
        """Un pellizco mantenido > hold_time debe disparar clic."""
        self.debouncer.update(is_pinching=True)
        # Simular que pasaron 200ms
        self.debouncer._pinch_start_time = time.time() - 0.2
        result = self.debouncer.update(is_pinching=True)
        self.assertTrue(result)

    def test_cooldown_prevents_rapid_clicks(self):
        """Después de un clic, el cooldown debe prevenir clics inmediatos."""
        # Forzar un clic
        self.debouncer.update(is_pinching=True)
        self.debouncer._pinch_start_time = time.time() - 0.2
        first = self.debouncer.update(is_pinching=True)
        self.assertTrue(first)

        # Soltar y volver a pellizcar inmediatamente — debe estar en cooldown
        self.debouncer.update(is_pinching=False)
        self.debouncer.update(is_pinching=True)
        self.debouncer._pinch_start_time = time.time() - 0.2
        second = self.debouncer.update(is_pinching=True)
        self.assertFalse(second)

    def test_click_after_cooldown_passes(self):
        """Después de que pasa el cooldown, debe permitir un nuevo clic."""
        self.debouncer.update(is_pinching=True)
        self.debouncer._pinch_start_time = time.time() - 0.2
        self.debouncer.update(is_pinching=True)  # triggers click

        # Simular que pasó el cooldown
        self.debouncer._last_click_time = time.time() - 0.4
        self.debouncer._clicked = False
        self.debouncer.update(is_pinching=False)

        # Nuevo pellizco
        self.debouncer.update(is_pinching=True)
        self.debouncer._pinch_start_time = time.time() - 0.2
        result = self.debouncer.update(is_pinching=True)
        self.assertTrue(result)


class TestGestureController(unittest.TestCase):
    """Pruebas para el controlador principal de gestos."""

    def setUp(self):
        from gesture_controller import GestureController
        # Crear controlador sin ejecutar acciones reales de pyautogui
        self.controller = GestureController(
            screen_width=1920,
            screen_height=1080,
            execute_actions=False  # Modo test: no mueve el mouse real
        )

    def test_fist_is_rest_mode(self):
        """Puño cerrado = modo reposo, no mueve cursor."""
        fingers = [0, 0, 0, 0, 0]
        action = self.controller.process_gesture(fingers, landmarks=None, frame_w=640, frame_h=480, frame_margin=100)
        self.assertEqual(action["mode"], "REPOSO")
        self.assertFalse(action["moved_cursor"])

    def test_index_only_is_pointer_mode(self):
        """Solo índice levantado = modo puntero, mueve cursor."""
        from test_hand_detector import create_mock_hand
        hand = create_mock_hand(False, True, False, False, False, handedness="Right")
        fingers = [0, 1, 0, 0, 0]
        action = self.controller.process_gesture(fingers, landmarks=hand, frame_w=640, frame_h=480, frame_margin=100)
        self.assertEqual(action["mode"], "PUNTERO")
        self.assertTrue(action["moved_cursor"])

    def test_open_palm_is_rest_mode(self):
        """Palma abierta = modo reposo."""
        fingers = [1, 1, 1, 1, 1]
        action = self.controller.process_gesture(fingers, landmarks=None, frame_w=640, frame_h=480, frame_margin=100)
        self.assertEqual(action["mode"], "REPOSO")

    def test_two_fingers_is_scroll_mode(self):
        """Índice + medio = modo scroll."""
        from test_hand_detector import create_mock_hand
        hand = create_mock_hand(False, True, True, False, False, handedness="Right")
        fingers = [0, 1, 1, 0, 0]
        action = self.controller.process_gesture(fingers, landmarks=hand, frame_w=640, frame_h=480, frame_margin=100)
        self.assertEqual(action["mode"], "SCROLL")

    def test_no_hand_is_rest_mode(self):
        """Sin mano detectada = modo reposo."""
        action = self.controller.process_gesture(None, landmarks=None, frame_w=640, frame_h=480, frame_margin=100)
        self.assertEqual(action["mode"], "REPOSO")

    def test_pre_pinch_locks_cursor_position_preventing_drift(self):
        """Al iniciar el pellizco (< 58px), el cursor se congela evitando que el temblor o movimiento del dedo mueva el cursor."""
        class MockPt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        def make_hand(ix, iy, tx, ty):
            pts = [MockPt(0.5, 0.5) for _ in range(21)]
            pts[8] = MockPt(ix, iy)   # Índice
            pts[4] = MockPt(tx, ty)   # Pulgar
            pts[12] = MockPt(0.9, 0.9)
            return pts

        fingers = [0, 1, 0, 0, 0]

        # 1. Movimiento normal con dedos separados (distancia = 100px > 58px)
        # 100px en x a 640px de ancho = 100/640 ≈ 0.156
        hand_open = make_hand(0.5, 0.5, 0.5 + 100/640, 0.5)
        action1 = self.controller.process_gesture(fingers, hand_open, 640, 480, 100)
        self.assertEqual(action1["mode"], "PUNTERO")
        self.assertFalse(action1["cursor_locked"])
        self.assertTrue(action1["moved_cursor"])
        saved_x = action1["cursor_x"]
        saved_y = action1["cursor_y"]

        # 2. El usuario inicia el pellizco: distancia baja a 45px (< 58px)
        # Y el dedo índice se mueve ligeramente por el esfuerzo motor (drift a 0.53, 0.53)
        hand_pre_pinch = make_hand(0.53, 0.53, 0.53 + 45/640, 0.53)
        action2 = self.controller.process_gesture(fingers, hand_pre_pinch, 640, 480, 100)

        # Debe estar congelado exactamente en la posición previa (cero drift)
        self.assertTrue(action2["cursor_locked"])
        self.assertFalse(action2["moved_cursor"])
        self.assertEqual(action2["cursor_x"], saved_x)
        self.assertEqual(action2["cursor_y"], saved_y)

    def test_pinch_click_executes_at_locked_coordinates(self):
        """Cuando se dispara el clic, debe ejecutarse en las coordenadas congeladas y no en la posición desviada."""
        class MockPt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        def make_hand(ix, iy, tx, ty):
            pts = [MockPt(0.5, 0.5) for _ in range(21)]
            pts[8] = MockPt(ix, iy)
            pts[4] = MockPt(tx, ty)
            pts[12] = MockPt(0.9, 0.9)
            return pts

        fingers = [0, 1, 0, 0, 0]

        # Apuntar a un botón (distancia normal = 90px)
        hand_aim = make_hand(0.4, 0.4, 0.4 + 90/640, 0.4)
        action_aim = self.controller.process_gesture(fingers, hand_aim, 640, 480, 100)
        target_x = action_aim["cursor_x"]
        target_y = action_aim["cursor_y"]

        # Iniciar pellizco y desviar el dedo (distancia = 45px < 58px)
        hand_pre = make_hand(0.44, 0.44, 0.44 + 45/640, 0.44)
        self.controller.process_gesture(fingers, hand_pre, 640, 480, 100)

        # Completar contacto de pellizco (distancia = 20px < 38px)
        hand_contact = make_hand(0.46, 0.46, 0.46 + 20/640, 0.46)
        self.controller.process_gesture(fingers, hand_contact, 640, 480, 100)

        # Simular que se cumplió el hold_time del debouncer
        self.controller.left_click_debouncer._pinch_start_time = time.time() - 0.25
        action_click = self.controller.process_gesture(fingers, hand_contact, 640, 480, 100)

        # Clic ejecutado
        self.assertTrue(action_click["clicked"])
        # Coordenadas idénticas a target_x, target_y donde se apuntó
        self.assertEqual(action_click["cursor_x"], target_x)
        self.assertEqual(action_click["cursor_y"], target_y)

    def test_unpinch_restores_cursor_movement(self):
        """Al separar los dedos y pasar el tiempo post-clic, el cursor recupera el movimiento libre."""
        class MockPt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        def make_hand(ix, iy, tx, ty):
            pts = [MockPt(0.5, 0.5) for _ in range(21)]
            pts[8] = MockPt(ix, iy)
            pts[4] = MockPt(tx, ty)
            pts[12] = MockPt(0.9, 0.9)
            return pts

        fingers = [0, 1, 0, 0, 0]

        # Bloquear con pre-pinch
        hand_pre = make_hand(0.5, 0.5, 0.5 + 40/640, 0.5)
        self.controller.process_gesture(fingers, hand_pre, 640, 480, 100)
        self.assertTrue(self.controller.is_click_locked)

        # Separar dedos (distancia = 120px > 58px)
        hand_opened = make_hand(0.6, 0.6, 0.6 + 120/640, 0.6)
        action = self.controller.process_gesture(fingers, hand_opened, 640, 480, 100)

        self.assertFalse(action["cursor_locked"])
        self.assertTrue(action["moved_cursor"])


class TestOneEuroFilter(unittest.TestCase):
    """Pruebas unitarias para el algoritmo del Filtro One Euro (Casiez et al. CHI 2012)."""

    def setUp(self):
        from gesture_controller import OneEuroFilter, OneEuroFilter2D
        self.filter = OneEuroFilter(min_cutoff=1.0, beta=0.007, d_cutoff=1.0)
        self.filter2d = OneEuroFilter2D(min_cutoff=1.0, beta=0.007)

    def test_first_sample_returns_direct_value(self):
        """La primera muestra no debe tener retraso ni atenuación."""
        val = self.filter.filter(150.0, timestamp=0.0)
        self.assertEqual(val, 150.0)

    def test_low_speed_noise_reduction(self):
        """A baja velocidad (temblor estático +/- 3px), el filtro debe atenuar el ruido > 80%."""
        t = 0.0
        dt = 1.0 / 30.0
        self.filter.filter(100.0, timestamp=t)

        max_deviation = 0.0
        for i in range(1, 15):
            t += dt
            raw = 100.0 + (3.0 if i % 2 == 0 else -3.0)
            filtered = self.filter.filter(raw, timestamp=t)
            dev = abs(filtered - 100.0)
            if dev > max_deviation:
                max_deviation = dev

        # La desviación del valor filtrado debe ser significativamente menor que los 3.0px de temblor
        self.assertLess(max_deviation, 0.6)

    def test_high_speed_tracking_responsiveness(self):
        """A alta velocidad (movimiento rápido 1500 px/s), la frecuencia de corte sube y sigue el cursor."""
        t = 0.0
        dt = 1.0 / 30.0
        self.filter.filter(100.0, timestamp=t)

        # Simular rampa rápida: 50 px por cuadro (1500 px/s)
        filtered_val = 100.0
        for i in range(1, 15):
            t += dt
            raw = 100.0 + i * 50.0
            filtered_val = self.filter.filter(raw, timestamp=t)

        # Al final de la rampa el filtro debe estar siguiendo activamente sin quedarse congelado
        self.assertGreater(filtered_val, 600.0)

    def test_reset_clears_state(self):
        """Reset debe limpiar el historial interno."""
        self.filter.filter(200.0, timestamp=0.0)
        self.assertIsNotNone(self.filter.x_prev)
        self.filter.reset()
        self.assertIsNone(self.filter.x_prev)
        self.assertIsNone(self.filter.t_prev)

    def test_2d_filter_coordinates(self):
        """El filtro 2D debe procesar X e Y de forma sincronizada."""
        fx, fy = self.filter2d.filter(500.0, 300.0, timestamp=1.0)
        self.assertEqual(fx, 500.0)
        self.assertEqual(fy, 300.0)


class TestHysteresisPinchDetector(unittest.TestCase):
    """Pruebas unitarias para el detector con Histéresis Dual y Confirmación Temporal."""

    def setUp(self):
        from gesture_controller import HysteresisPinchDetector
        self.detector = HysteresisPinchDetector(
            t_on=0.32,
            t_off=0.45,
            t_pre=0.52,
            confirm_frames=2
        )

    def test_pre_pinch_detects_intention(self):
        """Distancia por debajo de t_pre activa pre_pinching para congelar el cursor."""
        res1 = self.detector.update(0.60)
        self.assertFalse(res1["pre_pinching"])
        self.assertFalse(res1["pinching"])

        res2 = self.detector.update(0.50)
        self.assertTrue(res2["pre_pinching"])
        self.assertFalse(res2["pinching"])

    def test_activation_requires_temporal_confirmation(self):
        """Un solo cuadro por debajo de t_on no activa el pellizco; requiere confirm_frames=2."""
        # Cuadro 1: d < t_on (0.25 < 0.32)
        res1 = self.detector.update(0.25)
        self.assertFalse(res1["pinching"])
        self.assertFalse(res1["just_pressed"])

        # Cuadro 2: confirmado
        res2 = self.detector.update(0.25)
        self.assertTrue(res2["pinching"])
        self.assertTrue(res2["just_pressed"])

    def test_spurious_single_frame_rejected(self):
        """Un cuadro espurio aislado por debajo de t_on no dispara clic si se abre en el siguiente."""
        res1 = self.detector.update(0.20)
        self.assertFalse(res1["pinching"])
        # Rebote espurio vuelve a abrir
        res2 = self.detector.update(0.60)
        self.assertFalse(res2["pinching"])

    def test_hysteresis_gap_preserves_pinch(self):
        """Una vez activo, si la distancia fluctúa entre t_on (0.32) y t_off (0.45), el pellizco NO se corta."""
        # Activar pellizco (2 cuadros)
        self.detector.update(0.25)
        self.detector.update(0.25)
        self.assertTrue(self.detector.is_pinching)

        # Oscilación de la mano dentro de la brecha de histéresis (ej. 0.38, 0.42, 0.35)
        res_mid1 = self.detector.update(0.38)
        self.assertTrue(res_mid1["pinching"])
        res_mid2 = self.detector.update(0.42)
        self.assertTrue(res_mid2["pinching"])
        res_mid3 = self.detector.update(0.35)
        self.assertTrue(res_mid3["pinching"])

    def test_release_requires_crossing_t_off(self):
        """Para liberar el pellizco debe superarse t_off (0.45) durante confirm_frames."""
        self.detector.update(0.25)
        self.detector.update(0.25)
        self.assertTrue(self.detector.is_pinching)

        # Subir a 0.48 (supera t_off) cuadro 1
        res1 = self.detector.update(0.48)
        self.assertTrue(res1["pinching"])  # Requiere confirmación temporal para soltar

        # Cuadro 2 supera t_off -> Liberado
        res2 = self.detector.update(0.48)
        self.assertFalse(res2["pinching"])
        self.assertTrue(res2["just_released"])


class TestAnchorPointStability(unittest.TestCase):
    """Pruebas para verificar que el anclaje en Landmark 5 es inmune a la flexión del índice."""

    def test_knuckle_landmark_5_stays_still_during_pinch(self):
        """
        Al hacer pellizco, la punta del índice (Landmark 8) se desplaza hacia el pulgar,
        pero el nudillo (Landmark 5) se mantiene estructuralmente estable.
        """
        from gesture_controller import GestureController

        class MockPt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        controller = GestureController(
            screen_width=1920,
            screen_height=1080,
            execute_actions=False,
            anchor_landmark_id=5
        )

        def make_hand(knuckle_x, knuckle_y, tip_x, tip_y, thumb_x, thumb_y):
            pts = [MockPt(0.5, 0.5) for _ in range(21)]
            pts[0] = MockPt(0.5, 0.8)                 # Muñeca
            pts[9] = MockPt(0.5, 0.5)                 # Nudillo medio (tamaño mano = 0.3 * 480 = 144px)
            pts[5] = MockPt(knuckle_x, knuckle_y)     # Nudillo índice (ANCLAJE)
            pts[8] = MockPt(tip_x, tip_y)             # Punta índice
            pts[4] = MockPt(thumb_x, thumb_y)         # Punta pulgar
            return pts

        fingers = [0, 1, 0, 0, 0]

        # 1. Mano en reposo apuntando a un objetivo: Nudillo en (0.45, 0.45), Punta en (0.50, 0.35)
        # Distancia pulgar-índice grande (abierto)
        hand_open = make_hand(0.45, 0.45, 0.50, 0.35, 0.65, 0.35)
        action_open = controller.process_gesture(fingers, hand_open, 640, 480, 100)
        aimed_x = action_open["cursor_x"]
        aimed_y = action_open["cursor_y"]

        # 2. El usuario flexiona el dedo índice para pellizcar:
        # La punta (Landmark 8) se mueve bruscamente a (0.58, 0.45) (desplazamiento de ~60px en la punta)
        # PERO el nudillo (Landmark 5) permanece en (0.45, 0.45)
        hand_pinched = make_hand(0.45, 0.45, 0.58, 0.45, 0.59, 0.45)
        action_pinch = controller.process_gesture(fingers, hand_pinched, 640, 480, 100)

        # La posición del cursor en pantalla DEBE permanecer en las coordenadas apuntadas por el nudillo
        self.assertEqual(action_pinch["cursor_x"], aimed_x)
        self.assertEqual(action_pinch["cursor_y"], aimed_y)


class TestDragDeadzoneAndNormalization(unittest.TestCase):
    """Pruebas de zona muerta de arrastre e invariancia a la distancia de la cámara."""

    def test_drag_deadzone_stationary_vs_drag(self):
        """Micro-movimiento (< 15px) mantiene clic estático; movimiento intencional (> 15px) activa arrastre."""
        from gesture_controller import GestureController

        class MockPt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        controller = GestureController(
            screen_width=1920,
            screen_height=1080,
            execute_actions=False,
            drag_deadzone_px=15
        )

        def make_hand(ax, ay, pinch_dist):
            pts = [MockPt(0.5, 0.5) for _ in range(21)]
            pts[0] = MockPt(0.5, 0.8)
            pts[9] = MockPt(0.5, 0.5)  # mano tamaño ~ 144px
            pts[5] = MockPt(ax, ay)    # anclaje
            pts[8] = MockPt(ax, ay)
            pts[4] = MockPt(ax + pinch_dist/640, ay)
            return pts

        fingers = [0, 1, 0, 0, 0]

        # Iniciar pellizco firme (distancia 15px) en posición inicial (0.4, 0.4)
        h1 = make_hand(0.4, 0.4, 15)
        controller.process_gesture(fingers, h1, 640, 480, 100)
        controller.process_gesture(fingers, h1, 640, 480, 100)

        # Pequeño temblor de 5px (5/640 ≈ 0.0078) -> Menor que la zona muerta de arrastre (15px)
        h_tremor = make_hand(0.4 + 5/640, 0.4, 15)
        act_tremor = controller.process_gesture(fingers, h_tremor, 640, 480, 100)
        self.assertFalse(act_tremor["is_dragging"])
        self.assertTrue(act_tremor["cursor_locked"])

        # Movimiento deliberado de 30px (30/640 ≈ 0.0468) -> Mayor que zona muerta (15px)
        h_drag = make_hand(0.4 + 30/640, 0.4, 15)
        act_drag = controller.process_gesture(fingers, h_drag, 640, 480, 100)
        self.assertTrue(act_drag["is_dragging"])
        self.assertFalse(act_drag["cursor_locked"])

    def test_scale_invariance_normalized_distance(self):
        """Verifica que manos grandes (cerca) y pequeñas (lejos) activen el pellizco al mismo porcentaje relativo."""
        from gesture_controller import GestureController

        class MockPt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        controller = GestureController(screen_width=1920, screen_height=1080, execute_actions=False)

        def make_scaled_hand(hand_size_px, pinch_ratio):
            pts = [MockPt(0.5, 0.5) for _ in range(21)]
            # Muñeca y nudillo medio separados por hand_size_px
            pts[0] = MockPt(0.5, 0.5)
            pts[9] = MockPt(0.5, 0.5 + hand_size_px / 480.0)
            pts[5] = MockPt(0.5, 0.5)
            # Puntas separadas por hand_size_px * pinch_ratio
            pts[8] = MockPt(0.5, 0.5)
            pts[4] = MockPt(0.5 + (hand_size_px * pinch_ratio) / 640.0, 0.5)
            return pts

        fingers = [0, 1, 0, 0, 0]

        # Caso A: Mano grande / cerca (tamaño = 180px, relación = 0.22 < t_on 0.32)
        hand_close = make_scaled_hand(180, 0.22)
        controller.process_gesture(fingers, hand_close, 640, 480, 100)
        res_close = controller.process_gesture(fingers, hand_close, 640, 480, 100)
        self.assertTrue(res_close["cursor_locked"])
        self.assertAlmostEqual(res_close["normalized_dist"], 0.22, delta=0.03)

        # Resetear
        controller.process_gesture(None, None, 640, 480, 100)

        # Caso B: Mano pequeña / lejos (tamaño = 60px, misma relación = 0.22 < t_on 0.32)
        hand_far = make_scaled_hand(60, 0.22)
        controller.process_gesture(fingers, hand_far, 640, 480, 100)
        res_far = controller.process_gesture(fingers, hand_far, 640, 480, 100)
        self.assertTrue(res_far["cursor_locked"])
        self.assertAlmostEqual(res_far["normalized_dist"], 0.22, delta=0.03)

    def test_active_bounds_reach_all_four_screen_corners(self):
        """Verifica que el mapeo con active_bounds alcance con exactitud las cuatro esquinas de la pantalla."""
        from gesture_controller import GestureController

        class MockPt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        controller = GestureController(screen_width=1920, screen_height=1080, execute_actions=False)
        fingers = [0, 1, 0, 0, 0]

        # Definir zona activa delimitada (x1=150, x2=490, y1=120, y2=340)
        bounds = (150, 490, 120, 340)

        def make_at_pos(px_x, px_y):
            pts = [MockPt(0.5, 0.5) for _ in range(21)]
            pts[0] = MockPt(0.5, 0.8)
            pts[9] = MockPt(0.5, 0.5)  # hand_size ~ 144px
            pts[5] = MockPt(px_x / 640.0, px_y / 480.0) # anclaje en píxeles exactos
            pts[8] = MockPt(px_x / 640.0, (px_y - 60) / 480.0)
            pts[4] = MockPt((px_x + 80) / 640.0, px_y / 480.0) # pulgar bien separado (sin pre-pinch)
            return pts

        # 1. Esquina superior izquierda (x=150, y=120) -> Pantalla (0, 0)
        controller.smoother.reset()
        res_tl = controller.process_gesture(fingers, make_at_pos(150, 120), 640, 480, bounds)
        self.assertEqual(res_tl["cursor_x"], 0)
        self.assertEqual(res_tl["cursor_y"], 0)

        # 2. Esquina superior derecha (x=490, y=120) -> Pantalla (1919, 0)
        controller.smoother.reset()
        res_tr = controller.process_gesture(fingers, make_at_pos(490, 120), 640, 480, bounds)
        self.assertEqual(res_tr["cursor_x"], 1919)
        self.assertEqual(res_tr["cursor_y"], 0)

        # 3. Esquina inferior izquierda (x=150, y=340) -> Pantalla (0, 1079)
        controller.smoother.reset()
        res_bl = controller.process_gesture(fingers, make_at_pos(150, 340), 640, 480, bounds)
        self.assertEqual(res_bl["cursor_x"], 0)
        self.assertEqual(res_bl["cursor_y"], 1079)

        # 4. Esquina inferior derecha (x=490, y=340) -> Pantalla (1919, 1079)
        controller.smoother.reset()
        res_br = controller.process_gesture(fingers, make_at_pos(490, 340), 640, 480, bounds)
        self.assertEqual(res_br["cursor_x"], 1919)
        self.assertEqual(res_br["cursor_y"], 1079)

        # 5. Más allá del borde (clamp seguro) (x=50 < 150, y=50 < 120) -> (0, 0)
        controller.smoother.reset()
        res_over = controller.process_gesture(fingers, make_at_pos(50, 50), 640, 480, bounds)
        self.assertEqual(res_over["cursor_x"], 0)
        self.assertEqual(res_over["cursor_y"], 0)

    def test_no_false_pre_pinch_locking_during_normal_pointer(self):
        """Verifica que una mano a distancia natural con dedos abiertos no se congele accidentalmente."""
        from gesture_controller import GestureController

        class MockPt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        controller = GestureController(screen_width=1920, screen_height=1080, execute_actions=False)
        fingers = [0, 1, 0, 0, 0]

        # Mano con tamaño real de 80px
        pts = [MockPt(0.5, 0.5) for _ in range(21)]
        pts[0] = MockPt(0.5, 0.5)
        pts[9] = MockPt(0.5, 0.5 + 80.0 / 480.0) # tamaño = 80px
        pts[5] = MockPt(0.5, 0.5)
        pts[8] = MockPt(0.5, 0.4)
        # Pulgar a 52px del índice (52/80 = 0.65 > t_pre 0.52)
        pts[4] = MockPt(0.5 + 52.0 / 640.0, 0.4)

        action = controller.process_gesture(fingers, pts, 640, 480, 100)
        # El cursor DEBE moverse libremente sin congelamiento espurio
        self.assertFalse(action["cursor_locked"])
        self.assertTrue(action["moved_cursor"])


if __name__ == '__main__':
    unittest.main()

