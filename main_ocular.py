"""
Modo Ocular: Control de Cursor por Mirada y Clics por Parpadeo Intencional.
Proyecto Semestral — Tópicos Especiales I (Visión Artificial) — UTP 2026.

Integra:
1. MediaPipe Face Mesh con refine_landmarks=True para estimación de mirada.
2. Filtro One Euro para suavizado del cursor en pantalla.
3. Módulo desacoplado BlinkDetector:
   - Detección de parpadeo intencional mediante EAR sin filtrar.
   - Compensación vertical por mirada inferior.
   - Filtro anti-toque de Midas (velocidad sacádica + congelamiento deque).
   - Máquina de estados en tiempo real (0.35 s - 0.75 s).
"""

import time
import cv2
import pyautogui
import numpy as np
import mediapipe as mp
from mediapipe.python.solutions import face_mesh as mp_face_mesh

from gesture_controller import OneEuroFilter2D
from blink_detector import BlinkDetector


def initialize_camera(width=640, height=480):
    """Inicializa la cámara web."""
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not cap.isOpened():
        raise RuntimeError("Error: No se pudo acceder a la cámara web.")
    return cap


def initialize_face_mesh():
    """Inicializa MediaPipe Face Mesh con landmarks de iris refinados."""
    return mp_face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6
    )


def compute_gaze_screen_pos(landmarks, screen_width, screen_height, cursor_filter,
                            timestamp, margin_x=0.08, margin_y=0.08):
    """
    Calcula la coordenada de pantalla (x, y) suavizada con Filtro One Euro a partir
    de los centroides de iris (landmarks 468 y 473), acotada lejos de las esquinas
    para prevenir FailSafeException de PyAutoGUI.
    """
    iris_r = landmarks[468]
    iris_l = landmarks[473]
    iris_cx = (iris_r.x + iris_l.x) / 2.0
    iris_cy = (iris_r.y + iris_l.y) / 2.0

    norm_x = np.clip((iris_cx - (0.5 - margin_x)) / (2.0 * margin_x), 0.0, 1.0)
    norm_y = np.clip((iris_cy - (0.5 - margin_y)) / (2.0 * margin_y), 0.0, 1.0)

    target_screen_x = int(norm_x * screen_width)
    target_screen_y = int(norm_y * screen_height)

    smooth_x, smooth_y = cursor_filter.filter(
        target_screen_x, target_screen_y, timestamp=timestamp
    )
    smooth_x = int(np.clip(smooth_x, 1, screen_width - 2))
    smooth_y = int(np.clip(smooth_y, 1, screen_height - 2))
    return smooth_x, smooth_y, (iris_r, iris_l)


def main():
    """Bucle principal de control ocular."""
    pyautogui.PAUSE = 0
    screen_width, screen_height = pyautogui.size()
    cap = initialize_camera()
    face_mesh = initialize_face_mesh()

    # Filtro One Euro para suavizar exclusivamente la trayectoria del cursor
    cursor_filter = OneEuroFilter2D(min_cutoff=1.2, beta=0.015)

    # Detector de parpadeo intencional (EAR sin filtrar)
    blink_detector = BlinkDetector(
        close_factor=0.60,
        open_factor=0.75,
        y_comp_factor=0.20,
        speed_threshold_px_s=750.0,
        min_blink_duration_s=0.35,
        max_blink_duration_s=0.75,
        cancel_duration_s=0.80,
        cooldown_duration_s=0.40,
        calibration_frames=30,
        execute_click=True
    )

    p_time = 0.0

    print("=" * 60)
    print("  Modo Ocular — Control por Mirada y Clics por Parpadeo")
    print("=" * 60)
    print("  - Mirar a la pantalla    -> Control del cursor (One Euro)")
    print("  - Parpadeo 0.35s - 0.75s -> Clic izquierdo en posicion congelada")
    print("  - Parpadeo rapido <0.30s -> Ignorado (involuntario)")
    print("  - Cierre prolongado >0.8s-> Cancelado (descanso ocular)")
    print("  - Presionar 'q' o 'Esc'  -> Salir")
    print("=" * 60)

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            frame_h, frame_w, _ = frame.shape

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb_frame)

            current_time = time.perf_counter()

            if results.multi_face_landmarks:
                face_landmarks = results.multi_face_landmarks[0]
                landmarks = face_landmarks.landmark

                smooth_x, smooth_y, (iris_r, iris_l) = compute_gaze_screen_pos(
                    landmarks=landmarks,
                    screen_width=screen_width,
                    screen_height=screen_height,
                    cursor_filter=cursor_filter,
                    timestamp=current_time
                )

                # Actualización de la máquina de detección de parpadeo intencional
                blink_res = blink_detector.update(
                    landmarks=landmarks,
                    cursor_pos=(smooth_x, smooth_y),
                    screen_size=(screen_width, screen_height),
                    timestamp=current_time,
                    frame_size=(frame_w, frame_h)
                )

                # Mover cursor solo si no está congelado por cierre palpebral
                if blink_res["allow_movement"]:
                    pyautogui.moveTo(smooth_x, smooth_y)

                # Dibujar HUD de telemetría de parpadeo
                blink_detector.draw_hud(frame, blink_res, x=15, y=15)

                # Dibujar puntos de referencia del iris en la cámara
                for pt in [iris_r, iris_l]:
                    px = int(pt.x * frame_w)
                    py = int(pt.y * frame_h)
                    cv2.circle(frame, (px, py), 3, (0, 255, 255), -1)

            # Cálculo de FPS
            fps = 1.0 / (current_time - p_time) if (current_time - p_time) > 0 else 0
            p_time = current_time
            cv2.putText(frame, f"FPS: {int(fps)}", (frame_w - 110, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 128), 2)

            cv2.imshow("Modo Ocular - Vision Artificial (UTP)", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break
            elif key == ord('r'):
                blink_detector.reset_calibration()

    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Modo ocular finalizado.")


if __name__ == "__main__":
    main()
