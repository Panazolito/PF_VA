import cv2
import numpy as np
import time
import pyautogui
import mediapipe as mp
from mediapipe.python.solutions import hands as mp_hands
from mediapipe.python.solutions import drawing_utils as mp_drawing
from mediapipe.python.solutions import drawing_styles as mp_drawing_styles

# Desactivar la protección de bordes de PyAutoGUI
pyautogui.FAILSAFE = False

# 1. Configuración de MediaPipe Hands
hands_detector = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

# 2. Obtener la resolución de la pantalla
screen_width, screen_height = pyautogui.size()

# 3. Inicializar Cámara Web
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Margen en píxeles para la zona activa de la cámara
frame_margin = 100 

p_time = 0
click_estado = False
last_screen_x, last_screen_y = 0, 0

print("Presiona 'q' para salir")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Error: No se pudo acceder a la cámara")
        break

    # Volteo horizontal para efecto espejo
    frame = cv2.flip(frame, 1)
    frame_h, frame_w, _ = frame.shape

    # Dibujar un recuadro verde
    cv2.rectangle(
        frame, 
        (frame_margin, frame_margin), 
        (frame_w - frame_margin, frame_h - frame_margin), 
        (0, 255, 0), 
        2
    )

    # Convertir a RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands_detector.process(rgb_frame)

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            # Dibujar marcas de la mano
            mp_drawing.draw_landmarks(
                frame,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS,
                mp_drawing_styles.get_default_hand_landmarks_style(),
                mp_drawing_styles.get_default_hand_connections_style()
            )

            # Obtener puntos del Índice (8) y Pulgar (4)
            idx_finger = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            thumb_finger = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]

            x_idx, y_idx = int(idx_finger.x * frame_w), int(idx_finger.y * frame_h)
            x_thumb, y_thumb = int(thumb_finger.x * frame_w), int(thumb_finger.y * frame_h)

            # Distancia entre la punta del índice y el pulgar
            distancia = np.hypot(x_idx - x_thumb, y_idx - y_thumb)
            cv2.line(frame, (x_idx, y_idx), (x_thumb, y_thumb), (255, 0, 0), 2)

            # Mapeo considerando únicamente la zona activa interna
            if distancia > 45:
                # Mapear de [frame_margin, frame_w - frame_margin] a [0, screen_width]
                screen_x = np.interp(x_idx, (frame_margin, frame_w - frame_margin), (0, screen_width))
                screen_y = np.interp(y_idx, (frame_margin, frame_h - frame_margin), (0, screen_height))
                
                # Restringir las coordenadas al rango estricto de la pantalla
                screen_x = int(np.clip(screen_x, 0, screen_width - 1))
                screen_y = int(np.clip(screen_y, 0, screen_height - 1))

                last_screen_x, last_screen_y = screen_x, screen_y
                pyautogui.moveTo(screen_x, screen_y)
            else:
                pyautogui.moveTo(last_screen_x, last_screen_y)

            # Clic cuando la distancia es menor a 30 píxeles
            if distancia < 30:
                cv2.circle(frame, (x_idx, y_idx), 10, (0, 255, 0), cv2.FILLED)
                if not click_estado:
                    pyautogui.click()
                    click_estado = True
            else:
                click_estado = False

    # Cálculo de FPS
    c_time = time.time()
    fps = 1 / (c_time - p_time) if (c_time - p_time) > 0 else 0
    p_time = c_time

    cv2.putText(frame, f"FPS: {int(fps)}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow("Avance 1 - Visión Artificial (Hand Tracking)", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()