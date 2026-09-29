"""
Tests unitarios para el módulo user_lock.py
Valida la máquina de estados de bloqueo de usuario activo,
selección de mano más cercana, y transiciones de estado.
"""
import unittest
import time
from dataclasses import dataclass


@dataclass
class MockLandmark:
    x: float
    y: float
    z: float = 0.0


def create_mock_hand_at(center_x, center_y):
    """
    Crea una lista de 21 landmarks simulados centrados en (center_x, center_y).
    Las coordenadas están normalizadas (0.0 a 1.0).
    """
    landmarks = []
    for i in range(21):
        # Pequeña variación alrededor del centro para simular forma de mano
        offset_x = (i % 5 - 2) * 0.02
        offset_y = (i // 5 - 2) * 0.03
        landmarks.append(MockLandmark(
            x=center_x + offset_x,
            y=center_y + offset_y
        ))
    return landmarks


def create_mock_hand_with_span(center_x, center_y, span_scale=1.0):
    """Crea landmarks con escala configurable para simular manos más cercanas o lejanas."""
    landmarks = []
    for i in range(21):
        offset_x = (i % 5 - 2) * 0.02 * span_scale
        offset_y = (i // 5 - 2) * 0.03 * span_scale
        landmarks.append(MockLandmark(
            x=center_x + offset_x,
            y=center_y + offset_y
        ))
    return landmarks


class MockHandedness:
    """Simula el objeto de clasificación de handedness de MediaPipe."""
    def __init__(self, label="Right"):
        self.classification = [type('obj', (object,), {'label': label})()]


class MockNormalizedLandmarkList:
    """
    Simula un objeto NormalizedLandmarkList real de MediaPipe / Protobuf.
    No es iterable directamente (raise TypeError) ni subscriptable directamente;
    sus landmarks residen exclusivamente en el atributo .landmark.
    """
    def __init__(self, landmarks):
        self.landmark = landmarks

    def __iter__(self):
        raise TypeError("'NormalizedLandmarkList' object is not iterable")

    def __getitem__(self, item):
        raise TypeError("'NormalizedLandmarkList' object is not subscriptable")


class TestUserLockStates(unittest.TestCase):
    """Pruebas para las transiciones de estado de UserLock."""

    def setUp(self):
        from user_lock import UserLock
        self.lock = UserLock(
            activation_time_s=0.5,   # Más corto para tests
            reactivation_time_s=0.2,
            lost_timeout_s=1.0,
            pause_timeout_s=2.0,
            pause_gesture_time_s=0.5,
            continuity_threshold_px=150
        )

    def test_initial_state_is_inactive(self):
        """El estado inicial debe ser INACTIVO."""
        self.assertEqual(self.lock.state, "INACTIVO")

    def test_no_hands_stays_inactive(self):
        """Sin manos detectadas, el estado debe permanecer INACTIVO."""
        result = self.lock.update(
            all_hands=None,
            all_handedness=None,
            all_fingers=[],
            frame_w=640, frame_h=480
        )
        self.assertEqual(result["state"], "INACTIVO")
        self.assertIsNone(result["active_hand"])

    def test_palm_starts_activation(self):
        """Palma abierta debe iniciar estado ACTIVANDO."""
        hand = create_mock_hand_at(0.5, 0.5)
        fingers = [1, 1, 1, 1, 1]
        result = self.lock.update(
            all_hands=[hand],
            all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers],
            frame_w=640, frame_h=480
        )
        self.assertEqual(result["state"], "ACTIVANDO")
        self.assertGreater(result["activation_progress"], 0.0)

    def test_sustained_palm_activates(self):
        """Palma abierta sostenida >= activation_time debe activar."""
        hand = create_mock_hand_at(0.5, 0.5)
        fingers = [1, 1, 1, 1, 1]

        # Primera llamada: empieza activación
        self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers], frame_w=640, frame_h=480
        )

        # Simular que pasó el tiempo de activación
        self.lock._activation_start_time = time.time() - 0.6

        result = self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers], frame_w=640, frame_h=480
        )
        self.assertEqual(result["state"], "ACTIVO")
        self.assertIsNotNone(result["active_hand"])

    def test_interrupted_activation_returns_inactive(self):
        """Si el gesto de activación se interrumpe, vuelve a INACTIVO."""
        hand = create_mock_hand_at(0.5, 0.5)
        palm_fingers = [1, 1, 1, 1, 1]
        fist_fingers = [0, 0, 0, 0, 0]

        # Empezar activación
        self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[palm_fingers], frame_w=640, frame_h=480
        )
        self.assertEqual(self.lock.state, "ACTIVANDO")

        # Interrumpir con puño
        result = self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[fist_fingers], frame_w=640, frame_h=480
        )
        self.assertEqual(result["state"], "INACTIVO")

    def test_active_hand_disappears_goes_to_lost(self):
        """Si la mano activa desaparece, el estado cambia a PERDIDO."""
        hand = create_mock_hand_at(0.5, 0.5)
        fingers = [1, 1, 1, 1, 1]

        # Activar
        self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers], frame_w=640, frame_h=480
        )
        self.lock._activation_start_time = time.time() - 0.6
        self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers], frame_w=640, frame_h=480
        )
        self.assertEqual(self.lock.state, "ACTIVO")

        # Mano desaparece
        result = self.lock.update(
            all_hands=None, all_handedness=None,
            all_fingers=[], frame_w=640, frame_h=480
        )
        self.assertEqual(result["state"], "PERDIDO")

    def test_lost_timeout_returns_inactive(self):
        """Después del timeout en estado PERDIDO, vuelve a INACTIVO."""
        hand = create_mock_hand_at(0.5, 0.5)
        fingers = [1, 1, 1, 1, 1]

        # Activar
        self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers], frame_w=640, frame_h=480
        )
        self.lock._activation_start_time = time.time() - 0.6
        self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers], frame_w=640, frame_h=480
        )

        # Mano desaparece
        self.lock.update(
            all_hands=None, all_handedness=None,
            all_fingers=[], frame_w=640, frame_h=480
        )

        # Simular timeout
        self.lock._lost_start_time = time.time() - 1.5

        result = self.lock.update(
            all_hands=None, all_handedness=None,
            all_fingers=[], frame_w=640, frame_h=480
        )
        self.assertEqual(result["state"], "INACTIVO")

    def test_lost_reappears_before_timeout_returns_active(self):
        """Si la mano reaparece antes del timeout dentro del umbral, vuelve a ACTIVO."""
        hand = create_mock_hand_at(0.5, 0.5)
        fingers = [1, 1, 1, 1, 1]

        # Activar
        self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers], frame_w=640, frame_h=480
        )
        self.lock._activation_start_time = time.time() - 0.6
        self.lock.update(
            all_hands=[hand], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers], frame_w=640, frame_h=480
        )

        # Desaparece a PERDIDO
        self.lock.update(all_hands=None, all_handedness=None, all_fingers=[], frame_w=640, frame_h=480)
        self.assertEqual(self.lock.state, "PERDIDO")

        # Reaparece en posición cercana (0.51, 0.51) antes del timeout
        hand_reappeared = create_mock_hand_at(0.51, 0.51)
        result = self.lock.update(
            all_hands=[hand_reappeared],
            all_handedness=[MockHandedness("Right")],
            all_fingers=[[0, 1, 0, 0, 0]],
            frame_w=640, frame_h=480
        )
        self.assertEqual(result["state"], "ACTIVO")
        self.assertIsNotNone(result["active_hand"])

    def test_pause_mode_and_reactivation(self):
        """Verifica la transición a PAUSADO con puño y reactivación con palma."""
        hand = create_mock_hand_at(0.5, 0.5)
        fingers_palm = [1, 1, 1, 1, 1]
        fingers_fist = [0, 0, 0, 0, 0]

        # Activar
        self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_palm], frame_w=640, frame_h=480)
        self.lock._activation_start_time = time.time() - 0.6
        self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_palm], frame_w=640, frame_h=480)
        self.assertEqual(self.lock.state, "ACTIVO")

        # Puño cerrado por pause_gesture_time_s
        self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_fist], frame_w=640, frame_h=480)
        self.lock._pause_gesture_start = time.time() - 0.6
        result = self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_fist], frame_w=640, frame_h=480)
        self.assertEqual(result["state"], "PAUSADO")

        # Reactivación desde pausa con palma abierta
        self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_palm], frame_w=640, frame_h=480)
        self.lock._activation_start_time = time.time() - 0.3
        result_reactivated = self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_palm], frame_w=640, frame_h=480)
        self.assertEqual(result_reactivated["state"], "ACTIVO")

    def test_pause_timeout_returns_inactive(self):
        """Después del pause_timeout, el sistema retorna a INACTIVO."""
        hand = create_mock_hand_at(0.5, 0.5)
        fingers_palm = [1, 1, 1, 1, 1]
        fingers_fist = [0, 0, 0, 0, 0]

        # Activar y pausar
        self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_palm], frame_w=640, frame_h=480)
        self.lock._activation_start_time = time.time() - 0.6
        self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_palm], frame_w=640, frame_h=480)
        self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_fist], frame_w=640, frame_h=480)
        self.lock._pause_gesture_start = time.time() - 0.6
        self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_fist], frame_w=640, frame_h=480)
        self.assertEqual(self.lock.state, "PAUSADO")

        # Simular timeout en pausa
        self.lock._pause_start_time = time.time() - 3.0
        result = self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers_fist], frame_w=640, frame_h=480)
        self.assertEqual(result["state"], "INACTIVO")


class TestUserLockContinuity(unittest.TestCase):
    """Pruebas para la selección de mano por continuidad espacial y área."""

    def setUp(self):
        from user_lock import UserLock
        self.lock = UserLock(
            activation_time_s=0.1,
            lost_timeout_s=1.0,
            continuity_threshold_px=150
        )

    def test_closest_hand_selected_when_active(self):
        """Entre múltiples manos, se selecciona la más cercana al centroide anterior."""
        fingers_palm = [1, 1, 1, 1, 1]
        fingers_other = [0, 1, 0, 0, 0]

        # Activar con mano en (0.5, 0.5)
        hand_user = create_mock_hand_at(0.5, 0.5)
        self.lock.update(
            all_hands=[hand_user], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers_palm], frame_w=640, frame_h=480
        )
        self.lock._activation_start_time = time.time() - 0.2
        self.lock.update(
            all_hands=[hand_user], all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers_palm], frame_w=640, frame_h=480
        )
        self.assertEqual(self.lock.state, "ACTIVO")

        # Ahora hay dos manos: la del usuario (ligeramente movida) y un intruso lejos
        hand_user_moved = create_mock_hand_at(0.52, 0.48)
        hand_intruder = create_mock_hand_at(0.1, 0.1)

        result = self.lock.update(
            all_hands=[hand_intruder, hand_user_moved],
            all_handedness=[MockHandedness("Left"), MockHandedness("Right")],
            all_fingers=[fingers_other, fingers_palm],
            frame_w=640, frame_h=480
        )

        # Debe seleccionar hand_user_moved (más cercana), no hand_intruder
        self.assertEqual(result["state"], "ACTIVO")
        self.assertIsNotNone(result["active_hand"])

    def test_multiple_palms_prioritizes_larger_hand(self):
        """Si dos personas muestran palma abierta a la vez en INACTIVO, se prioriza la mano más grande (más cercana)."""
        hand_close = create_mock_hand_with_span(0.5, 0.5, span_scale=2.0)  # Persona en primer plano
        hand_far = create_mock_hand_with_span(0.2, 0.2, span_scale=0.8)    # Persona en segundo plano
        fingers = [1, 1, 1, 1, 1]

        result = self.lock.update(
            all_hands=[hand_far, hand_close],
            all_handedness=[MockHandedness("Left"), MockHandedness("Right")],
            all_fingers=[fingers, fingers],
            frame_w=640, frame_h=480
        )

        self.assertEqual(result["state"], "ACTIVANDO")
        # El centroide bloqueado debe corresponder a la mano cercana (alrededor de 320 px, no 128 px)
        self.assertAlmostEqual(self.lock._locked_centroid[0], 320.0, delta=25.0)

    def test_activating_hand_moved_out_of_threshold_cancels(self):
        """Si la mano salta bruscamente durante la activación (> 150px), la activación se cancela."""
        hand = create_mock_hand_at(0.5, 0.5)
        fingers = [1, 1, 1, 1, 1]

        # Iniciar activación
        self.lock.update(all_hands=[hand], all_handedness=[MockHandedness("Right")], all_fingers=[fingers], frame_w=640, frame_h=480)
        self.assertEqual(self.lock.state, "ACTIVANDO")

        # Mano salta a otra esquina del cuadro (> 150 px de distancia)
        hand_jumped = create_mock_hand_at(0.1, 0.1)
        result = self.lock.update(all_hands=[hand_jumped], all_handedness=[MockHandedness("Right")], all_fingers=[fingers], frame_w=640, frame_h=480)
        self.assertEqual(result["state"], "INACTIVO")

    def test_draw_lock_status_renders_correctly(self):
        """Verifica que draw_lock_status renderice sobre una imagen OpenCV sin excepciones."""
        import numpy as np
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Probar en cada uno de los estados
        for state in ["INACTIVO", "ACTIVANDO", "ACTIVO", "PERDIDO", "PAUSADO"]:
            self.lock._state = state
            self.lock._locked_centroid = (320, 240)
            rendered = self.lock.draw_lock_status(dummy_frame.copy(), num_hands=2)
            self.assertEqual(rendered.shape, (480, 640, 3))

    def test_handles_mediapipe_normalized_landmark_list(self):
        """Verifica que UserLock maneje correctamente objetos NormalizedLandmarkList reales de MediaPipe."""
        raw_landmarks = create_mock_hand_at(0.5, 0.5)
        mp_hand = MockNormalizedLandmarkList(raw_landmarks)
        fingers = [1, 1, 1, 1, 1]

        # En estado INACTIVO, debe calcular área y centroide sin lanzar TypeError
        result = self.lock.update(
            all_hands=[mp_hand],
            all_handedness=[MockHandedness("Right")],
            all_fingers=[fingers],
            frame_w=640,
            frame_h=480
        )
        self.assertEqual(result["state"], "ACTIVANDO")


if __name__ == '__main__':
    unittest.main()
