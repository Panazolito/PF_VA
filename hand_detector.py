"""
Módulo de Detección de Dedos y Gestos para Visión Artificial.
Desarrollado para el proyecto semestral de Visión Artificial (UTP).
"""

import cv2
import numpy as np


# Índices de Landmarks de MediaPipe Hands
# Puntas de los dedos (TIP)
FINGER_TIPS = [4, 8, 12, 16, 20]
# Articulaciones de referencia (PIP / IP)
FINGER_PIPS = [3, 6, 10, 14, 18]

# Nombres legibles de los dedos
FINGER_NAMES = ["Pulgar", "Índice", "Medio", "Anular", "Meñique"]
FINGER_SHORT_NAMES = ["P", "I", "M", "A", "Mñ"]


def get_fingers_up(landmarks, handedness="Right"):
    """
    Determina qué dedos están levantados/extendidos.
    
    Args:
        landmarks: Lista de 21 landmarks de MediaPipe (con atributos .x, .y, .z).
        handedness: "Right" o "Left" indicando la mano detectada.
                    Nota: en modo espejo (cv2.flip(frame, 1)), MediaPipe clasifica
                    la mano como se ve en la pantalla.
    
    Returns:
        list[int]: Lista de 5 valores binarios [pulgar, índice, medio, anular, meñique],
                   donde 1 indica dedo levantado y 0 dedo doblado.
    """
    if hasattr(landmarks, "landmark"):
        landmarks = landmarks.landmark

    fingers = []

    # 1. Detección del Pulgar (Landmark 4 TIP vs Landmark 2 MCP)
    # Se compara contra el MCP (landmark 2) en vez del IP (landmark 3)
    # porque es más robusto cuando la mano rota parcialmente.
    if handedness == "Right":
        # En la imagen espejo, para la mano derecha el pulgar extendido apunta hacia la izquierda (x menor)
        is_thumb_up = landmarks[4].x < landmarks[2].x
    else:
        # Para la mano izquierda, el pulgar extendido apunta hacia la derecha (x mayor)
        is_thumb_up = landmarks[4].x > landmarks[2].x
        
    fingers.append(1 if is_thumb_up else 0)


    # 2. Detección de los otros 4 dedos (Índice, Medio, Anular, Meñique)
    # Se compara la posición Y de la punta (TIP) con la articulación PIP (dedo levantado = y menor en OpenCV)
    for tip_id, pip_id in zip(FINGER_TIPS[1:], FINGER_PIPS[1:]):
        if landmarks[tip_id].y < landmarks[pip_id].y:
            fingers.append(1)
        else:
            fingers.append(0)

    return fingers


def get_gesture_name(fingers):
    """
    Identifica un nombre descriptivo para la combinación de dedos levantados.
    
    Args:
        fingers: Lista de 5 enteros [pulgar, índice, medio, anular, meñique].
    
    Returns:
        str: Nombre amigable del gesto detectado.
    """
    total = sum(fingers)
    
    if fingers == [0, 0, 0, 0, 0]:
        return "Puño cerrado"
    elif fingers == [1, 1, 1, 1, 1]:
        return "Palma abierta"
    elif fingers == [0, 1, 0, 0, 0]:
        return "Puntero (Índice)"
    elif fingers == [0, 1, 1, 0, 0]:
        return "Victoria / Scroll"
    elif fingers == [1, 0, 0, 0, 0]:
        return "Pulgar arriba"
    elif fingers == [0, 1, 1, 1, 0]:
        return "Tres dedos"
    elif fingers == [0, 1, 1, 1, 1]:
        return "Cuatro dedos"
    elif fingers == [1, 1, 0, 0, 0]:
        return "Gesto L"
    elif fingers == [1, 1, 0, 0, 1]:
        return "Rock / Cuernos"
    elif fingers == [1, 0, 0, 0, 1]:
        return "Llamada / Shaka"
    elif fingers == [0, 0, 0, 0, 1]:
        return "Meñique"
    else:
        return f"{total} dedos levantados"


def draw_hud(frame, fingers=None, gesture_name="", fps=0, handedness=None, mode="",
             cursor_locked=False, is_dragging=False, sensitivity=1.0):
    """
    Dibuja un panel HUD moderno y semitransparente con información de los dedos y gestos.
    
    Args:
        frame: Imagen OpenCV (BGR) sobre la que se dibuja.
        fingers: Lista de 5 enteros [pulgar, índice, medio, anular, meñique] o None.
        gesture_name: Nombre del gesto activo.
        fps: Tasa de cuadros por segundo.
        handedness: "Right" o "Left", o None si no hay mano detectada.
        mode: Modo activo del controlador ("PUNTERO", "SCROLL", "REPOSO", "CLIC_DERECHO").
        cursor_locked: Si True, indica que el cursor está congelado para evitar drift al clickear.
        is_dragging: Si True, indica que se está realizando un arrastre activo (mouseDown).
        sensitivity: Multiplicador de sensibilidad actual (ej. 1.3x).
    """
    h, w, _ = frame.shape
    
    # Crear capa superpuesta para transparencia (efecto panel oscuro translúcido)
    overlay = frame.copy()
    panel_w, panel_h = 295, 175
    cv2.rectangle(overlay, (15, 15), (15 + panel_w, 15 + panel_h), (25, 25, 25), -1)
    # Mezcla con transparencia alfa = 0.75
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    
    # Borde sutil del panel
    cv2.rectangle(frame, (15, 15), (15 + panel_w, 15 + panel_h), (80, 80, 80), 1)

    # 1. FPS, Mano y Sensibilidad
    mano_txt = "Mano: " + ("Der" if handedness == "Right" else ("Izq" if handedness == "Left" else "--"))
    cv2.putText(frame, f"FPS: {int(fps)}", (25, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 128), 2)
    cv2.putText(frame, mano_txt, (108, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)
    cv2.putText(frame, f"Sens: {sensitivity:.1f}x", (195, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 255), 1)

    # Separador
    cv2.line(frame, (25, 52), (15 + panel_w - 10, 52), (60, 60, 60), 1)

    if fingers is not None:
        total = sum(fingers)
        # 2. Gesto actual y conteo
        cv2.putText(frame, f"Gesto: {gesture_name}", (25, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)
        cv2.putText(frame, f"Dedos: {total}/5", (25, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1)

        # 3. Modo activo con badge de color y estado de fijación / arrastre
        if mode:
            mode_colors = {
                "PUNTERO": (0, 255, 0),       # Verde
                "SCROLL": (255, 165, 0),       # Naranja
                "REPOSO": (100, 100, 100),     # Gris
                "CLIC_DERECHO": (0, 180, 255), # Amarillo-naranja
            }
            mode_color = mode_colors.get(mode, (200, 200, 200))
            if is_dragging:
                mode_str = f"Modo: {mode} [ARRASTRE]"
                mode_color = (255, 255, 0)  # Cyan brillante para arrastre
            elif cursor_locked:
                mode_str = f"Modo: {mode} [FIJADO]"
                mode_color = (0, 215, 255)  # Ámbar/dorado de posición fijada
            else:
                mode_str = f"Modo: {mode}"
            cv2.putText(frame, mode_str, (140, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.38, mode_color, 2)

        # 4. Badges individuales de los dedos: P, I, M, A, Mñ
        start_x = 30
        spacing = 48
        y_badge = 155
        
        for i, (name, is_up) in enumerate(zip(FINGER_SHORT_NAMES, fingers)):
            cx = start_x + (i * spacing)
            color = (0, 230, 0) if is_up else (60, 60, 200) # Verde si levantado, Rojo oscuro si doblado
            
            # Círculo indicador
            cv2.circle(frame, (cx + 10, y_badge - 8), 12, color, -1)
            # Letra del dedo
            cv2.putText(frame, name, (cx + (4 if len(name) == 1 else 0), y_badge - 3), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
    else:
        cv2.putText(frame, "Esperando mano...", (25, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 100, 255), 1)
        if mode:
            cv2.putText(frame, f"Modo: {mode}", (25, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 100), 1)

    return frame
