import unittest
from dataclasses import dataclass

# Simulación de un landmark de MediaPipe con coordenadas x, y, z
@dataclass
class MockLandmark:
    x: float
    y: float
    z: float = 0.0


def create_mock_hand(
    thumb_up=True,
    index_up=True,
    middle_up=True,
    ring_up=True,
    pinky_up=True,
    handedness="Right"
):
    """
    Crea una lista de 21 landmarks sintéticos para simular una mano con los dedos especificados.
    Para una mano derecha con palma hacia la cámara (vista espejo):
    - El pulgar extendido apunta hacia la izquierda (x menor).
    - Los dedos levantados tienen TIP.y < PIP.y.
    - Los dedos doblados tienen TIP.y > PIP.y.
    """
    landmarks = [MockLandmark(0.5, 0.9) for _ in range(21)] # Inicializar todos

    # Muñeca
    landmarks[0] = MockLandmark(0.5, 0.9)

    # Pulgar (Landmarks 1, 2, 3, 4)
    landmarks[1] = MockLandmark(0.48, 0.8) # CMC
    landmarks[2] = MockLandmark(0.45, 0.7) # MCP
    landmarks[3] = MockLandmark(0.42, 0.6) # IP
    if handedness == "Right":
        # Mano derecha en espejo: pulgar extendido a la izquierda (x < ip.x)
        landmarks[4] = MockLandmark(0.30 if thumb_up else 0.46, 0.55 if thumb_up else 0.70)
    else:
        # Mano izquierda en espejo: pulgar extendido a la derecha (x > ip.x)
        landmarks[4] = MockLandmark(0.54 if thumb_up else 0.40, 0.55 if thumb_up else 0.70)

    # Índice (5: MCP, 6: PIP, 7: DIP, 8: TIP)
    landmarks[5] = MockLandmark(0.45, 0.6)
    landmarks[6] = MockLandmark(0.45, 0.5)
    landmarks[7] = MockLandmark(0.45, 0.4)
    landmarks[8] = MockLandmark(0.45, 0.3 if index_up else 0.65)

    # Medio (9: MCP, 10: PIP, 11: DIP, 12: TIP)
    landmarks[9] = MockLandmark(0.50, 0.6)
    landmarks[10] = MockLandmark(0.50, 0.5)
    landmarks[11] = MockLandmark(0.50, 0.4)
    landmarks[12] = MockLandmark(0.50, 0.3 if middle_up else 0.65)

    # Anular (13: MCP, 14: PIP, 15: DIP, 16: TIP)
    landmarks[13] = MockLandmark(0.55, 0.6)
    landmarks[14] = MockLandmark(0.55, 0.5)
    landmarks[15] = MockLandmark(0.55, 0.4)
    landmarks[16] = MockLandmark(0.55, 0.3 if ring_up else 0.65)

    # Meñique (17: MCP, 18: PIP, 19: DIP, 20: TIP)
    landmarks[17] = MockLandmark(0.60, 0.6)
    landmarks[18] = MockLandmark(0.60, 0.5)
    landmarks[19] = MockLandmark(0.60, 0.4)
    landmarks[20] = MockLandmark(0.60, 0.3 if pinky_up else 0.65)

    return landmarks


class TestHandDetector(unittest.TestCase):

    def setUp(self):
        # Intentamos importar la función que debe existir en hand_detector
        import hand_detector
        self.get_fingers_up = hand_detector.get_fingers_up
        self.get_gesture_name = hand_detector.get_gesture_name

    def test_all_fingers_up(self):
        hand = create_mock_hand(True, True, True, True, True, handedness="Right")
        fingers = self.get_fingers_up(hand, handedness="Right")
        self.assertEqual(fingers, [1, 1, 1, 1, 1])
        self.assertEqual(self.get_gesture_name(fingers), "Palma abierta")

    def test_fist_all_fingers_down(self):
        hand = create_mock_hand(False, False, False, False, False, handedness="Right")
        fingers = self.get_fingers_up(hand, handedness="Right")
        self.assertEqual(fingers, [0, 0, 0, 0, 0])
        self.assertEqual(self.get_gesture_name(fingers), "Puño cerrado")

    def test_pointer_finger(self):
        hand = create_mock_hand(False, True, False, False, False, handedness="Right")
        fingers = self.get_fingers_up(hand, handedness="Right")
        self.assertEqual(fingers, [0, 1, 0, 0, 0])
        self.assertEqual(self.get_gesture_name(fingers), "Puntero (Índice)")

    def test_peace_scroll(self):
        hand = create_mock_hand(False, True, True, False, False, handedness="Right")
        fingers = self.get_fingers_up(hand, handedness="Right")
        self.assertEqual(fingers, [0, 1, 1, 0, 0])
        self.assertEqual(self.get_gesture_name(fingers), "Victoria / Scroll")

    def test_thumb_up(self):
        hand = create_mock_hand(True, False, False, False, False, handedness="Right")
        fingers = self.get_fingers_up(hand, handedness="Right")
        self.assertEqual(fingers, [1, 0, 0, 0, 0])
        self.assertEqual(self.get_gesture_name(fingers), "Pulgar arriba")

    def test_left_hand_thumb(self):
        # Para la mano izquierda, el pulgar extendido apunta a la derecha
        hand = create_mock_hand(True, True, False, False, False, handedness="Left")
        fingers = self.get_fingers_up(hand, handedness="Left")
        self.assertEqual(fingers, [1, 1, 0, 0, 0])

    def test_other_gestures(self):
        # Shaka / Llamada (pulgar y meñique)
        hand = create_mock_hand(True, False, False, False, True, handedness="Right")
        fingers = self.get_fingers_up(hand, handedness="Right")
        self.assertEqual(fingers, [1, 0, 0, 0, 1])
        self.assertEqual(self.get_gesture_name(fingers), "Llamada / Shaka")

        # Rock / Cuernos (pulgar, índice y meñique)
        hand = create_mock_hand(True, True, False, False, True, handedness="Right")
        fingers = self.get_fingers_up(hand, handedness="Right")
        self.assertEqual(fingers, [1, 1, 0, 0, 1])
        self.assertEqual(self.get_gesture_name(fingers), "Rock / Cuernos")

    def test_draw_hud(self):
        import hand_detector
        import numpy as np
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Probar con mano presente
        res_frame = hand_detector.draw_hud(dummy_frame.copy(), fingers=[0, 1, 0, 0, 0], gesture_name="Puntero", fps=30.0, handedness="Right")
        self.assertEqual(res_frame.shape, (480, 640, 3))
        # Probar sin mano presente
        res_frame_none = hand_detector.draw_hud(dummy_frame.copy(), fingers=None, fps=30.0)
        self.assertEqual(res_frame_none.shape, (480, 640, 3))


if __name__ == '__main__':
    unittest.main()

