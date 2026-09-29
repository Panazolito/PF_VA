"""
Control del Cursor y Gestos por Visión Artificial.
Proyecto Semestral — Tópicos Especiales I (Visión Artificial) — UTP 2026.

Utiliza MediaPipe Hands para detectar la mano del usuario frente a la cámara
y traduce los gestos en acciones del sistema operativo: mover cursor, clic
izquierdo, clic derecho y scroll.

Sistema de seguridad multi-persona:
    - Palma abierta 2s         → Activar control (bloqueo de usuario)
    - Puño cerrado 2s          → Pausar control
    - Mano desaparece 3s       → Liberar control automáticamente

Controles por gestos (una vez activado):
    - Solo índice levantado    → Modo PUNTERO (mover cursor)
    - Pellizco pulgar-índice   → Clic izquierdo (con debounce)
    - Índice + medio           → Modo SCROLL (subir/bajar = scroll)
    - Presionar 'q' o 'Esc'   → Salir del programa

Autores: Victor Sánchez, Crisarys Vasquez, Juan Gonzalez, Alexandra Esteves
"""

import cv2
import numpy as np
import time
import pyautogui
import mediapipe as mp
from mediapipe.python.solutions import hands as mp_hands
from mediapipe.python.solutions import drawing_utils as mp_drawing
from mediapipe.python.solutions import drawing_styles as mp_drawing_styles

from hand_detector import get_fingers_up, get_gesture_name, draw_hud
from gesture_controller import GestureController
from user_lock import UserLock


def initialize_camera(width=640, height=480):
    """Inicializa la cámara web con la resolución especificada."""
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not cap.isOpened():
        raise RuntimeError("Error: No se pudo acceder a la cámara web.")
    return cap


def initialize_hands_detector(max_hands=2):
    """Inicializa el detector de manos de MediaPipe.
    
    Args:
        max_hands: Número máximo de manos a detectar simultáneamente.
                   Se usa 2 para poder filtrar intrusos con UserLock.
    """
    return mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=max_hands,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7
    )


def main():
    """Bucle principal del programa de control por gestos."""

    # 1. Configuración
    screen_width, screen_height = pyautogui.size()
    cap = initialize_camera()
    hands_detector = initialize_hands_detector(max_hands=2)

    controller = GestureController(
        screen_width=screen_width,
        screen_height=screen_height,
        execute_actions=True,
        smoothing_factor=0.4,
        hold_time_ms=150,
        cooldown_ms=300
    )

    user_lock = UserLock(
        activation_time_s=2.0,
        reactivation_time_s=1.0,
        lost_timeout_s=3.0,
        pause_timeout_s=10.0,
        pause_gesture_time_s=2.0,
        continuity_threshold_px=150
    )

    # Sensibilidad inicial (1.3x permite alcanzar las 4 esquinas con movimiento de mano natural y relajado)
    sensitivity = 1.3
    p_time = 0

    print("=" * 55)
    print("  Control por Gestos — Visión Artificial (UTP)")
    print("=" * 55)
    print("  Activación:")
    print("    - Palma abierta 2s   → Activar control")
    print("    - Puño cerrado 2s    → Pausar control")
    print("  Gestos (una vez activado):")
    print("    - Solo índice        → Mover cursor (anclaje en nudillo L5)")
    print("    - Pellizco (P+I)     → Clic izquierdo (con posición fijada)")
    print("    - Pellizco + Mover   → Arrastrar elementos (Drag & Drop)")
    print("    - Pellizco (P+M)     → Clic derecho")
    print("    - Índice + medio     → Scroll vertical")
    print("  Ajustes en vivo:")
    print("    - Tecla '+' o 's'    → Aumentar sensibilidad (alcanzar esquinas fácilmente)")
    print("    - Tecla '-' o 'a'    → Reducir sensibilidad (mayor precisión)")
    print("    - 'q' o 'Esc'        → Salir del programa")
    print("=" * 55)

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("Error: No se pudo leer un frame de la cámara.")
                break

            # Volteo horizontal para efecto espejo
            frame = cv2.flip(frame, 1)
            frame_h, frame_w, _ = frame.shape

            # --- Zona activa ergonómica adaptada a la biomecánica de la mano ---
            # El centro se ajusta a la altura natural del nudillo (Landmark 5)
            cx = frame_w // 2
            cy = int(frame_h * 0.48)
            base_hw = int(frame_w * 0.32)  # ~205 px
            base_hh = int(frame_h * 0.28)  # ~134 px

            eff_hw = int(base_hw / sensitivity)
            eff_hh = int(base_hh / sensitivity)

            x1 = max(15, cx - eff_hw)
            x2 = min(frame_w - 15, cx + eff_hw)
            y1 = max(15, cy - eff_hh)
            y2 = min(frame_h - 15, cy + eff_hh)
            active_bounds = (x1, x2, y1, y2)

            # Dibujar recuadro de la zona activa que mapea a la pantalla completa
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"Zona Pantalla ({sensitivity:.1f}x) [+/-]", (x1 + 6, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 0), 1)

            # Convertir a RGB y procesar con MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands_detector.process(rgb_frame)

            # --- Paso 1: Detectar dedos de TODAS las manos ---
            all_hands = results.multi_hand_landmarks if results.multi_hand_landmarks else []
            all_handedness = results.multi_handedness if results.multi_handedness else []
            all_fingers = []

            for idx, hand_landmarks in enumerate(all_hands):
                # Dibujar marcas de TODAS las manos (con estilo atenuado para intrusos)
                mp_drawing.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style()
                )

                # Calcular dedos levantados para cada mano
                if idx < len(all_handedness):
                    h_label = all_handedness[idx].classification[0].label
                else:
                    h_label = "Right"
                fingers = get_fingers_up(hand_landmarks.landmark, handedness=h_label)
                all_fingers.append(fingers)

            # --- Paso 2: UserLock decide CUÁL mano es la del usuario activo ---
            lock_result = user_lock.update(
                all_hands=all_hands if all_hands else None,
                all_handedness=all_handedness if all_handedness else None,
                all_fingers=all_fingers,
                frame_w=frame_w,
                frame_h=frame_h
            )

            current_fingers = lock_result["active_fingers"]
            current_handedness = lock_result["handedness"]
            current_gesture = get_gesture_name(current_fingers) if current_fingers else ""
            active_hand = lock_result["active_hand"]
            action_result = None

            # --- Paso 3: Solo procesar gestos si hay usuario activo ---
            if active_hand is not None and lock_result["state"] == "ACTIVO":
                active_landmarks = active_hand.landmark if hasattr(active_hand, "landmark") else active_hand

                # Extraer world landmarks 3D si están disponibles
                active_idx = lock_result.get("active_index", None)
                all_world = results.multi_hand_world_landmarks if results.multi_hand_world_landmarks else None
                active_world = all_world[active_idx] if (all_world and active_idx is not None and active_idx < len(all_world)) else None

                action_result = controller.process_gesture(
                    fingers=current_fingers,
                    landmarks=active_landmarks,
                    frame_w=frame_w,
                    frame_h=frame_h,
                    frame_margin=active_bounds,
                    handedness=current_handedness or "Right",
                    world_landmarks=active_world
                )

                is_locked = action_result and action_result.get("cursor_locked", False)
                is_dragging = action_result and action_result.get("is_dragging", False)
                is_clicked = action_result and action_result.get("clicked", False)
                is_right_clicked = action_result and action_result.get("right_clicked", False)

                # Nudillo del índice (Landmark 5: Anclaje de seguimiento estable)
                knuckle = active_landmarks[5]
                kx, ky = int(knuckle.x * frame_w), int(knuckle.y * frame_h)
                cv2.circle(frame, (kx, ky), 5, (255, 180, 0), -1)

                # Indicador visual de arrastre activo
                if is_dragging:
                    cv2.circle(frame, (kx, ky), 22, (255, 255, 0), 2)
                    cv2.putText(frame, "ARRASTRE", (kx + 25, ky + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2)
                # Indicador visual de posición fijada (pre-pellizco anti-drift)
                elif is_locked and not is_clicked and not is_right_clicked:
                    cv2.circle(frame, (kx, ky), 18, (0, 215, 255), 2)
                    cv2.putText(frame, "FIJADO", (kx + 22, ky + 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 215, 255), 1)

                # Indicador visual de clic izquierdo
                if is_clicked:
                    idx_tip = active_landmarks[8]
                    cx = int(idx_tip.x * frame_w)
                    cy = int(idx_tip.y * frame_h)
                    cv2.circle(frame, (cx, cy), 20, (0, 255, 0), cv2.FILLED)
                    cv2.putText(frame, "CLIC!", (cx + 25, cy + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

                # Indicador visual de clic derecho
                if is_right_clicked:
                    mid_tip = active_landmarks[12]
                    cx = int(mid_tip.x * frame_w)
                    cy = int(mid_tip.y * frame_h)
                    cv2.circle(frame, (cx, cy), 20, (255, 0, 255), cv2.FILLED)
                    cv2.putText(frame, "CLIC DER!", (cx + 25, cy + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 0, 255), 2)
            else:
                # Sin usuario activo: resetear controlador
                controller.process_gesture(
                    fingers=None, landmarks=None,
                    frame_w=frame_w, frame_h=frame_h, frame_margin=active_bounds
                )

            # Cálculo de FPS
            c_time = time.time()
            fps = 1 / (c_time - p_time) if (c_time - p_time) > 0 else 0
            p_time = c_time

            # Dibujar HUD superior (gesto + dedos + modo + estado de fijación y arrastre)
            current_mode = controller.current_mode
            is_locked = action_result.get("cursor_locked", False) if action_result else False
            is_dragging = action_result.get("is_dragging", False) if action_result else False
            draw_hud(
                frame,
                fingers=current_fingers,
                gesture_name=current_gesture,
                fps=fps,
                handedness=current_handedness,
                mode=current_mode,
                cursor_locked=is_locked,
                is_dragging=is_dragging,
                sensitivity=sensitivity
            )

            # Dibujar panel de estado del bloqueo de usuario (inferior)
            user_lock.draw_lock_status(frame, num_hands=len(all_hands))

            cv2.imshow("Control por Gestos - Vision Artificial (UTP)", frame)

            # Control por teclado
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break
            elif key in (ord('+'), ord('='), ord('s'), ord('S')):
                sensitivity = min(2.5, round(sensitivity + 0.1, 1))
            elif key in (ord('-'), ord('_'), ord('a'), ord('A')):
                sensitivity = max(0.7, round(sensitivity - 0.1, 1))

    except KeyboardInterrupt:
        print("\nPrograma interrumpido por el usuario.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Cámara liberada. Programa finalizado.")


if __name__ == "__main__":
    main()