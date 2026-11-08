"""
Interfaz Gráfica de Inicio: Pantalla de Carga (con video circular y música) y Menú Principal.
Proyecto Semestral — Tópicos Especiales I (Visión Artificial) — UTP 2026.

Incluye:
- Pantalla de carga de 3 segundos en estilo Vinotinto Oscuro, con barra de progreso animada,
  reproducción circular de Dino/DinoVideo.mp4 (sin bordes negros laterales) y música MusicaFondo.mp3
  a volumen alto que disminuye automáticamente al pasar al menú.
- Menú principal con 3 opciones:
    1. Empezar -> Abre submenú para elegir entre "Manos + Mirada" o "Solo Mirada"
    2. Configuraciones -> Permite subir o bajar la sensibilidad ocular del cursor
    3. Controles -> Abre submenú para elegir entre controles de "Manos + Mirada" o "Solo Mirada"
"""

import os
import time
import ctypes
import tkinter as tk
import cv2
import numpy as np
from PIL import Image, ImageTk, ImageDraw


# Paleta de colores Vinotinto Más Oscuro (Elegante y Profundo)
BG_VINOTINTO_DARK = "#1B0306"      # Fondo principal vinotinto muy oscuro
BG_VINOTINTO_PANEL = "#2B060B"     # Paneles / contenedores interiores vinotinto oscuro
BG_VINOTINTO_CARD = "#380910"      # Tarjetas de controles / filas
BG_BUTTON = "#4D0D17"              # Color base de botón vinotinto oscuro
BG_BUTTON_HOVER = "#6B1421"        # Color hover de botón
BG_ACCENT_GOLD = "#F2C94C"         # Dorado cálido para barras, títulos y bordes activos
BG_ACCENT_GREEN = "#27AE60"        # Verde esmeralda para acción principal
TEXT_PRIMARY = "#FFF5F6"           # Blanco cálido
TEXT_SECONDARY = "#DDB4BA"         # Rosa/crema suave para subtítulos
BORDER_COLOR = "#631521"           # Borde vinotinto oscuro elegante


class BackgroundMusicController:
    """Controlador de audio MP3 nativo en Windows mediante API MCI (winmm)."""

    def __init__(self, mp3_path):
        self.mp3_path = mp3_path
        self.alias = "dino_bgm"
        self.is_playing = False
        self._winmm = getattr(ctypes, "windll", None)
        self._mci = self._winmm.winmm.mciSendStringW if self._winmm else None

    def _send(self, command):
        if not self._mci:
            return
        try:
            buf = ctypes.create_unicode_buffer(255)
            self._mci(command, buf, 254, 0)
        except Exception:
            pass

    def start(self, volume=1000):
        """Inicia la música en bucle con el volumen indicado (0 a 1000)."""
        if not os.path.exists(self.mp3_path):
            return
        self.stop()
        self._send(f'open "{self.mp3_path}" type mpegvideo alias {self.alias}')
        self.set_volume(volume)
        self._send(f"play {self.alias} repeat")
        self.is_playing = True

    def set_volume(self, volume):
        """Ajusta el volumen entre 0 y 1000."""
        vol = max(0, min(1000, int(volume)))
        self._send(f"setaudio {self.alias} volume to {vol}")

    def stop(self):
        """Detiene y cierra el recurso de audio."""
        if self.is_playing:
            self._send(f"stop {self.alias}")
            self._send(f"close {self.alias}")
            self.is_playing = False


def load_circular_dino_image(image_path, size_px, bg_hex=BG_VINOTINTO_CARD, border_width=2):
    """
    Carga una imagen de Dino (que tiene un círculo central sobre fondo negro/blanco),
    recorta exactamente el círculo central y aplica una máscara circular suave anti-aliasing.
    """
    if not os.path.exists(image_path):
        fallback = Image.new("RGBA", (size_px, size_px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(fallback)
        draw.ellipse((2, 2, size_px - 3, size_px - 3), fill=bg_hex, outline="#FFFFFF", width=2)
        return ImageTk.PhotoImage(fallback)

    raw_bytes = np.fromfile(image_path, dtype=np.uint8)
    img_bgr = cv2.imdecode(raw_bytes, cv2.IMREAD_UNCHANGED)
    if img_bgr is None:
        fallback = Image.new("RGBA", (size_px, size_px), (0, 0, 0, 0))
        return ImageTk.PhotoImage(fallback)

    if img_bgr.shape[2] == 4:
        img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGRA2RGBA)
        pil_img = Image.fromarray(img_rgba, mode="RGBA")
    else:
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb, mode="RGB").convert("RGBA")

    w, h = pil_img.size
    cx = w // 2
    cy = h // 2
    radius = int(min(w, h) * 0.495)

    left = max(0, cx - radius)
    top = max(0, cy - radius)
    right = min(w, cx + radius)
    bottom = min(h, cy + radius)

    cropped = pil_img.crop((left, top, right, bottom))

    scale = 2
    hi_size = size_px * scale
    cropped_hi = cropped.resize((hi_size, hi_size), Image.Resampling.LANCZOS)

    mask = Image.new("L", (hi_size, hi_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    margin = 2 * scale
    mask_draw.ellipse((margin, margin, hi_size - margin - 1, hi_size - margin - 1), fill=255)

    bg_rgb = tuple(int(bg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    out_hi = Image.new("RGBA", (hi_size, hi_size), bg_rgb + (255,))
    out_hi.paste(cropped_hi, (0, 0), mask)

    if border_width > 0:
        ring_draw = ImageDraw.Draw(out_hi)
        ring_draw.ellipse(
            (margin, margin, hi_size - margin - 1, hi_size - margin - 1),
            outline=(255, 255, 255, 255),
            width=border_width * scale
        )

    final_img = out_hi.resize((size_px, size_px), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(final_img)


class CircularVideoPlayer:
    """
    Lee cuadros de DinoVideo.mp4, recorta únicamente el círculo central eliminando
    todo el borde negro de los lados y devuelve un ImageTk.PhotoImage circular.
    """

    def __init__(self, video_path, diameter_px, bg_hex=BG_VINOTINTO_DARK):
        self.video_path = video_path
        self.diameter_px = diameter_px
        self.bg_rgb = tuple(int(bg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        self.cap = None
        if os.path.exists(video_path):
            self.cap = cv2.VideoCapture(video_path)

        self.mask = np.zeros((diameter_px, diameter_px), dtype=np.uint8)
        center = diameter_px // 2
        radius = center - 2
        cv2.circle(self.mask, (center, center), radius, 255, -1, lineType=cv2.LINE_AA)
        self.mask_f = (self.mask.astype(np.float32) / 255.0)[..., None]

        self.bg_arr = np.full((diameter_px, diameter_px, 3), self.bg_rgb, dtype=np.float32)

    def get_next_frame_photo(self):
        """Obtiene el siguiente cuadro del video recortado en círculo sin bordes negros."""
        if self.cap is None or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                return None

        h, w, _ = frame.shape
        cx = int(w * 0.498)
        cy = h // 2
        r = int(min(w, h) * 0.485)

        x1 = max(0, cx - r)
        x2 = min(w, cx + r)
        y1 = max(0, cy - r)
        y2 = min(h, cy + r)

        cropped = frame[y1:y2, x1:x2]
        resized_bgr = cv2.resize(cropped, (self.diameter_px, self.diameter_px), interpolation=cv2.INTER_AREA)
        resized_rgb = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)

        blended = (resized_rgb * self.mask_f + self.bg_arr * (1.0 - self.mask_f)).astype(np.uint8)

        center = self.diameter_px // 2
        radius = center - 3
        cv2.circle(blended, (center, center), radius, (255, 255, 255), 3, lineType=cv2.LINE_AA)

        pil_img = Image.fromarray(blended)
        return ImageTk.PhotoImage(pil_img)

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class DinoMenuApp:
    """
    Aplicación gráfica de inicio:
    1) Pantalla de carga (3 segundos) con barra de progreso, DinoVideo circular y música alta.
    2) Menú principal con Empezar (submenú Manos + Mirada / Solo Mirada), Configuraciones y
       Controles (submenú Manos + Mirada / Solo Mirada).
    """

    def __init__(self, initial_sensitivity=1.3):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.dino_dir = os.path.join(self.base_dir, "Dino")
        self.sensitivity = float(initial_sensitivity)
        self.start_requested = False
        self.selected_mode = "manos_mirada"  # "manos_mirada" o "solo_mirada"

        # Rutas de recursos (carpeta Dino para imágenes y video, raíz para música)
        self.video_path = self._resolve_dino_asset("DinoVideo.mp4")
        self.music_path = os.path.join(self.base_dir, "MusicaFondo.mp3")
        self.dino_main_img_path = self._resolve_dino_asset("Dino1.jpg")

        puno_candidates = [
            os.path.join(self.dino_dir, "DinoPuñoCerrado.png"),
            os.path.join(self.base_dir, "DinoPuñoCerrado.png"),
        ]
        for search_dir in (self.dino_dir, self.base_dir):
            if os.path.isdir(search_dir):
                for fname in os.listdir(search_dir):
                    if fname.startswith("DinoPu") and fname.endswith(".png"):
                        puno_candidates.append(os.path.join(search_dir, fname))
        self.puno_path = puno_candidates[0]
        for c in puno_candidates:
            if os.path.exists(c):
                self.puno_path = c
                break

        self.control_items_data = [
            (
                "DinoManoAbierta.png",
                "Palma abierta 2s  →  Activar control",
                "Muestra los 5 dedos extendidos durante 2 segundos para bloquear tu sesión."
            ),
            (
                self.puno_path,
                "Puño cerrado 2s  →  Pausar control",
                "Cierra el puño por 2 segundos para congelar el sistema de forma segura."
            ),
            (
                "DinoDedoIndice.png",
                "Pellizco pulgar-índice  →  Clic izquierdo",
                "Une el pulgar y el índice para hacer clic donde apunta tu mirada (o arrastrar)."
            ),
            (
                "DinoDedoMedio.png",
                "Pellizco dedo medio-índice  →  Clic derecho",
                "Une el dedo medio con el pulgar (con índice arriba) para ejecutar clic derecho."
            ),
            (
                "DinoVictoria.png",
                "Levantar Índice + medio  →  Modo SCROLL",
                "Mantén el gesto de victoria quieto y mira hacia arriba o abajo para desplazar."
            ),
        ]

        self.gaze_control_items_data = [
            (
                "DinoOjosCerrados.png",
                "Dejar ambos ojos cerrados 2s  →  Activar / Reanudar el control",
                "Mantén ambos ojos cerrados durante 2 segundos para activar o reanudar el control."
            ),
            (
                "DinoSonrisa.png",
                "Sonreír por 2s  →  Pausar el control",
                "Mantén una sonrisa durante 2 segundos para pausar el sistema de forma segura."
            ),
            (
                "DinoOjoIzquierdo.png",
                "Guiñar ojo izquierdo  →  Clic izquierdo",
                "Cierra brevemente el ojo izquierdo (con el derecho abierto) para hacer clic izquierdo."
            ),
            (
                "DinoOjoDerecho.png",
                "Guiñar ojo derecho  →  Clic derecho",
                "Cierra brevemente el ojo derecho (con el izquierdo abierto) para ejecutar clic derecho."
            ),
            (
                "DinoLenguaAfuera.png",
                "Sacar la lengua  →  Modo SCROLL",
                "Mantén la lengua afuera y mueve tu mirada hacia arriba o abajo para desplazar."
            ),
        ]

        # Ventana Tkinter
        self.root = tk.Tk()
        self.root.title("Control Multimodal — Visión Artificial (UTP)")
        self.root.configure(bg=BG_VINOTINTO_DARK)
        self.root.resizable(False, False)

        # Centrar ventana de 1020x650 (más ancha horizontalmente para que ningún texto se corte)
        win_w, win_h = 1020, 650
        scr_w = self.root.winfo_screenwidth()
        scr_h = self.root.winfo_screenheight()
        pos_x = max(0, (scr_w - win_w) // 2)
        pos_y = max(0, (scr_h - win_h) // 2 - 20)
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

        # Controladores multimedia
        self.music = BackgroundMusicController(self.music_path)
        self.video_player = CircularVideoPlayer(self.video_path, diameter_px=270, bg_hex=BG_VINOTINTO_DARK)
        self._current_video_photo = None
        self._control_photos = []
        self._menu_dino_photo = None
        self._loading_active = False

        # Contenedor principal
        self.main_container = tk.Frame(self.root, bg=BG_VINOTINTO_DARK)
        self.main_container.pack(fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _resolve_dino_asset(self, filename):
        """Busca un recurso primero en la carpeta Dino/ y como respaldo en el directorio base."""
        if os.path.isabs(filename) and os.path.exists(filename):
            return filename
        in_dino = os.path.join(self.dino_dir, os.path.basename(filename))
        if os.path.exists(in_dino):
            return in_dino
        return os.path.join(self.base_dir, os.path.basename(filename))

    def _clear_container(self):
        self._loading_active = False
        for widget in self.main_container.winfo_children():
            widget.destroy()

    # =========================================================================
    # 1. PANTALLA DE CARGA (3 SEGUNDOS)
    # =========================================================================
    def show_loading_screen(self):
        self._clear_container()
        self._loading_active = True

        self.music.start(volume=1000)

        frame = tk.Frame(self.main_container, bg=BG_VINOTINTO_DARK)
        frame.pack(fill="both", expand=True, padx=40, pady=25)

        lbl_tag = tk.Label(
            frame,
            text="UNIVERSIDAD TECNOLÓGICA DE PANAMÁ • VISIÓN ARTIFICIAL",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_DARK
        )
        lbl_tag.pack(pady=(5, 4))

        lbl_title = tk.Label(
            frame,
            text="Sistema Multimodal Vista + Manos",
            font=("Segoe UI", 22, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_VINOTINTO_DARK
        )
        lbl_title.pack(pady=(0, 12))

        bar_card = tk.Frame(
            frame,
            bg=BG_VINOTINTO_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=2,
            padx=25,
            pady=18
        )
        bar_card.pack(fill="x", padx=60, pady=(4, 18))

        self.lbl_loading_status = tk.Label(
            bar_card,
            text="Cargando módulos de Visión Artificial... 0%",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_VINOTINTO_PANEL
        )
        self.lbl_loading_status.pack(anchor="w", pady=(0, 8))

        self.bar_width = 620
        self.bar_height = 24
        self.bar_canvas = tk.Canvas(
            bar_card,
            width=self.bar_width,
            height=self.bar_height,
            bg="#120204",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR
        )
        self.bar_canvas.pack()

        self.bar_fill_rect = self.bar_canvas.create_rectangle(
            0, 0, 0, self.bar_height,
            fill=BG_ACCENT_GOLD,
            width=0
        )

        video_holder = tk.Frame(frame, bg=BG_VINOTINTO_DARK)
        video_holder.pack(expand=True, pady=(5, 5))

        self.lbl_video = tk.Label(video_holder, bg=BG_VINOTINTO_DARK, bd=0)
        self.lbl_video.pack()

        lbl_hint = tk.Label(
            frame,
            text="Preparando seguimiento ocular y control gestual...",
            font=("Segoe UI", 10, "italic"),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_DARK
        )
        lbl_hint.pack(pady=(4, 0))

        self.loading_start_time = time.perf_counter()
        self.loading_duration_s = 3.0
        self._update_loading_tick()

    def _update_loading_tick(self):
        if not self._loading_active:
            return

        elapsed = time.perf_counter() - self.loading_start_time
        progress = min(1.0, elapsed / self.loading_duration_s)
        pct = int(progress * 100)

        fill_w = int(self.bar_width * progress)
        self.bar_canvas.coords(self.bar_fill_rect, 0, 0, fill_w, self.bar_height)
        self.lbl_loading_status.config(text=f"Cargando módulos de Visión Artificial... {pct}%")

        photo = self.video_player.get_next_frame_photo()
        if photo is not None:
            self._current_video_photo = photo
            self.lbl_video.config(image=photo)

        if elapsed < self.loading_duration_s:
            self.root.after(30, self._update_loading_tick)
        else:
            self._loading_active = False
            self.video_player.release()
            self._fade_music_to_menu_volume(current_vol=1000, target_vol=220)
            self.show_main_menu()

    def _fade_music_to_menu_volume(self, current_vol, target_vol):
        """Baja gradualmente el volumen al entrar al menú para una transición suave."""
        if not self.music.is_playing:
            return
        if current_vol <= target_vol:
            self.music.set_volume(target_vol)
            return
        next_vol = max(target_vol, current_vol - 130)
        self.music.set_volume(next_vol)
        self.root.after(45, lambda: self._fade_music_to_menu_volume(next_vol, target_vol))

    # =========================================================================
    # 2. MENÚ PRINCIPAL (Empezar | Configuraciones | Controles)
    # =========================================================================
    def show_main_menu(self):
        self._clear_container()

        frame = tk.Frame(self.main_container, bg=BG_VINOTINTO_DARK)
        frame.pack(fill="both", expand=True, padx=45, pady=24)

        header = tk.Frame(frame, bg=BG_VINOTINTO_DARK)
        header.pack(fill="x", pady=(0, 12))

        if self._menu_dino_photo is None:
            self._menu_dino_photo = load_circular_dino_image(
                self.dino_main_img_path, size_px=135, bg_hex=BG_VINOTINTO_DARK, border_width=3
            )

        lbl_logo = tk.Label(header, image=self._menu_dino_photo, bg=BG_VINOTINTO_DARK)
        lbl_logo.pack(pady=(0, 8))

        tk.Label(
            header,
            text="CONTROL MULTIMODAL POR VISIÓN ARTIFICIAL",
            font=("Segoe UI", 20, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_VINOTINTO_DARK
        ).pack()

        tk.Label(
            header,
            text=f"Sensibilidad ocular actual: {self.sensitivity:.1f}x   •   Rastreo de Iris + Gestos",
            font=("Segoe UI", 10),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_DARK
        ).pack(pady=(3, 0))

        menu_panel = tk.Frame(
            frame,
            bg=BG_VINOTINTO_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=2,
            padx=35,
            pady=24
        )
        menu_panel.pack(fill="x", padx=65, pady=10)

        self._create_menu_button(
            menu_panel,
            text="▶   Empezar",
            subtitle="Elegir modalidad (Manos + Mirada  o  Solo Mirada) e iniciar el sistema",
            command=self.show_start_mode_submenu,
            primary=True
        ).pack(fill="x", pady=(0, 14))

        self._create_menu_button(
            menu_panel,
            text="⚙   Configuraciones",
            subtitle=f"Ajustar la sensibilidad del cursor ocular (actual: {self.sensitivity:.1f}x)",
            command=self.show_settings_screen
        ).pack(fill="x", pady=(0, 14))

        self._create_menu_button(
            menu_panel,
            text="✋   Controles",
            subtitle="Consultar los gestos y comandos de Manos + Mirada o Solo Mirada",
            command=self.show_controls_mode_submenu
        ).pack(fill="x", pady=(0, 4))

        btn_exit = tk.Button(
            frame,
            text="Salir del programa",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_DARK,
            activebackground=BG_VINOTINTO_PANEL,
            activeforeground=TEXT_PRIMARY,
            bd=0,
            cursor="hand2",
            command=self._on_close
        )
        btn_exit.pack(pady=(8, 0))

    # =========================================================================
    # 2.1 SUBMENÚ AL PRESIONAR "EMPEZAR": (Manos + Mirada | Solo Mirada)
    # =========================================================================
    def show_start_mode_submenu(self):
        self._clear_container()

        frame = tk.Frame(self.main_container, bg=BG_VINOTINTO_DARK)
        frame.pack(fill="both", expand=True, padx=45, pady=28)

        header = tk.Frame(frame, bg=BG_VINOTINTO_DARK)
        header.pack(fill="x", pady=(0, 14))

        if self._menu_dino_photo is None:
            self._menu_dino_photo = load_circular_dino_image(
                self.dino_main_img_path, size_px=125, bg_hex=BG_VINOTINTO_DARK, border_width=3
            )

        tk.Label(header, image=self._menu_dino_photo, bg=BG_VINOTINTO_DARK).pack(pady=(0, 10))

        tk.Label(
            header,
            text="SELECCIONA EL MODO DE EJECUCIÓN",
            font=("Segoe UI", 19, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_VINOTINTO_DARK
        ).pack()

        tk.Label(
            header,
            text="Elige cómo deseas controlar el cursor y las acciones del sistema:",
            font=("Segoe UI", 10),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_DARK
        ).pack(pady=(4, 0))

        sub_panel = tk.Frame(
            frame,
            bg=BG_VINOTINTO_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=2,
            padx=35,
            pady=28
        )
        sub_panel.pack(fill="x", padx=65, pady=16)

        self._create_menu_button(
            sub_panel,
            text="🖐️ + 👁️   Manos + Mirada",
            subtitle="Mover el cursor con la vista y ejecutar clics, scroll y pausa con gestos de la mano",
            command=lambda: self._start_with_mode("manos_mirada"),
            primary=True
        ).pack(fill="x", pady=(0, 16))

        self._create_menu_button(
            sub_panel,
            text="👁️   Solo Mirada",
            subtitle="Mover el cursor con la vista, clic con guiños, scroll con la lengua y pausa sonriendo",
            command=lambda: self._start_with_mode("solo_mirada"),
            primary=True
        ).pack(fill="x", pady=(0, 4))

        btn_back = tk.Button(
            frame,
            text="←   Volver al Menú Principal",
            font=("Segoe UI", 11, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_BUTTON,
            activebackground=BG_BUTTON_HOVER,
            activeforeground=TEXT_PRIMARY,
            padx=22,
            pady=8,
            bd=0,
            cursor="hand2",
            command=self.show_main_menu
        )
        btn_back.pack(pady=(12, 0))

    def _create_menu_button(self, parent, text, subtitle, command, primary=False):
        bg_norm = "#5C101C" if primary else BG_BUTTON
        bg_hov = "#7D1727" if primary else BG_BUTTON_HOVER
        border_col = BG_ACCENT_GOLD if primary else BORDER_COLOR

        card = tk.Frame(
            parent,
            bg=bg_norm,
            highlightbackground=border_col,
            highlightthickness=2 if primary else 1,
            padx=18,
            pady=11,
            cursor="hand2"
        )

        lbl_main = tk.Label(
            card,
            text=text,
            font=("Segoe UI", 14, "bold"),
            fg=TEXT_PRIMARY,
            bg=bg_norm,
            anchor="w",
            cursor="hand2"
        )
        lbl_main.pack(fill="x")

        lbl_sub = tk.Label(
            card,
            text=subtitle,
            font=("Segoe UI", 9),
            fg=TEXT_SECONDARY,
            bg=bg_norm,
            anchor="w",
            cursor="hand2"
        )
        lbl_sub.pack(fill="x", pady=(2, 0))

        def on_enter(_e):
            card.config(bg=bg_hov)
            lbl_main.config(bg=bg_hov)
            lbl_sub.config(bg=bg_hov)

        def on_leave(_e):
            card.config(bg=bg_norm)
            lbl_main.config(bg_norm)
            lbl_sub.config(bg_norm)

        for w in (card, lbl_main, lbl_sub):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda _e: command())

        return card

    # =========================================================================
    # 3. PANTALLA DE CONFIGURACIONES (Sensibilidad del Cursor)
    # =========================================================================
    def show_settings_screen(self):
        self._clear_container()

        frame = tk.Frame(self.main_container, bg=BG_VINOTINTO_DARK)
        frame.pack(fill="both", expand=True, padx=50, pady=28)

        tk.Label(
            frame,
            text="⚙  CONFIGURACIONES",
            font=("Segoe UI", 20, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_VINOTINTO_DARK
        ).pack(pady=(0, 6))

        tk.Label(
            frame,
            text="Ajusta la sensibilidad del cursor al moverlo con la vista según el tamaño de tu pantalla",
            font=("Segoe UI", 10),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_DARK
        ).pack(pady=(0, 18))

        panel = tk.Frame(
            frame,
            bg=BG_VINOTINTO_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=2,
            padx=32,
            pady=26
        )
        panel.pack(fill="x", padx=40)

        tk.Label(
            panel,
            text="Sensibilidad Ocular del Cursor",
            font=("Segoe UI", 13, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_VINOTINTO_PANEL
        ).pack()

        self.lbl_sens_value = tk.Label(
            panel,
            text=f"{self.sensitivity:.1f}x",
            font=("Segoe UI", 30, "bold"),
            fg=BG_ACCENT_GOLD,
            bg=BG_VINOTINTO_PANEL
        )
        self.lbl_sens_value.pack(pady=(8, 10))

        ctrl_row = tk.Frame(panel, bg=BG_VINOTINTO_PANEL)
        ctrl_row.pack(fill="x", pady=6)

        btn_minus = tk.Button(
            ctrl_row,
            text="−",
            font=("Segoe UI", 16, "bold"),
            width=3,
            fg=TEXT_PRIMARY,
            bg=BG_BUTTON,
            activebackground=BG_BUTTON_HOVER,
            activeforeground=TEXT_PRIMARY,
            bd=0,
            cursor="hand2",
            command=lambda: self._adjust_sensitivity(-0.1)
        )
        btn_minus.pack(side="left", padx=(10, 14))

        self.sens_scale = tk.Scale(
            ctrl_row,
            from_=0.7,
            to=2.5,
            resolution=0.1,
            orient="horizontal",
            bg=BG_VINOTINTO_PANEL,
            fg=TEXT_PRIMARY,
            troughcolor="#120204",
            activebackground=BG_ACCENT_GOLD,
            highlightthickness=0,
            showvalue=False,
            command=self._on_slider_change
        )
        self.sens_scale.set(self.sensitivity)
        self.sens_scale.pack(side="left", fill="x", expand=True)

        btn_plus = tk.Button(
            ctrl_row,
            text="+",
            font=("Segoe UI", 16, "bold"),
            width=3,
            fg=TEXT_PRIMARY,
            bg=BG_BUTTON,
            activebackground=BG_BUTTON_HOVER,
            activeforeground=TEXT_PRIMARY,
            bd=0,
            cursor="hand2",
            command=lambda: self._adjust_sensitivity(+0.1)
        )
        btn_plus.pack(side="left", padx=(14, 10))

        presets_frame = tk.Frame(panel, bg=BG_VINOTINTO_PANEL)
        presets_frame.pack(pady=(16, 6))

        presets = [
            ("Suave (0.9x)", 0.9),
            ("Estándar (1.3x)", 1.3),
            ("Rápida (1.7x)", 1.7),
            ("Monitor Grande (2.1x)", 2.1),
        ]
        for label_txt, val in presets:
            b = tk.Button(
                presets_frame,
                text=label_txt,
                font=("Segoe UI", 9, "bold"),
                fg=TEXT_PRIMARY,
                bg=BG_VINOTINTO_CARD,
                activebackground=BG_BUTTON_HOVER,
                activeforeground=TEXT_PRIMARY,
                padx=10,
                pady=5,
                bd=1,
                relief="solid",
                cursor="hand2",
                command=lambda v=val: self._set_sensitivity(v)
            )
            b.pack(side="left", padx=5)

        tk.Label(
            panel,
            text="Nota: Durante la ejecución también puedes ajustar en vivo con las teclas '+' / 's' y '-' / 'a'.",
            font=("Segoe UI", 9, "italic"),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_PANEL,
            wraplength=720
        ).pack(pady=(14, 0))

        btn_back = tk.Button(
            frame,
            text="←   Guardar y Volver al Menú",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_BUTTON,
            activebackground=BG_BUTTON_HOVER,
            activeforeground=TEXT_PRIMARY,
            padx=24,
            pady=10,
            bd=0,
            cursor="hand2",
            command=self.show_main_menu
        )
        btn_back.pack(pady=(24, 0))

    def _on_slider_change(self, val):
        self.sensitivity = round(float(val), 1)
        if hasattr(self, "lbl_sens_value"):
            self.lbl_sens_value.config(text=f"{self.sensitivity:.1f}x")

    def _adjust_sensitivity(self, delta):
        new_val = max(0.7, min(2.5, round(self.sensitivity + delta, 1)))
        self._set_sensitivity(new_val)

    def _set_sensitivity(self, val):
        self.sensitivity = round(float(val), 1)
        self.sens_scale.set(self.sensitivity)
        self.lbl_sens_value.config(text=f"{self.sensitivity:.1f}x")

    # =========================================================================
    # 4. SUBMENÚ Y PANTALLAS DE CONTROLES (Manos + Mirada | Solo Mirada)
    # =========================================================================
    def show_controls_mode_submenu(self):
        """Submenú intermedio de Controles para elegir entre Manos + Mirada o Solo Mirada."""
        self._clear_container()

        frame = tk.Frame(self.main_container, bg=BG_VINOTINTO_DARK)
        frame.pack(fill="both", expand=True, padx=45, pady=28)

        header = tk.Frame(frame, bg=BG_VINOTINTO_DARK)
        header.pack(fill="x", pady=(0, 14))

        if self._menu_dino_photo is None:
            self._menu_dino_photo = load_circular_dino_image(
                self.dino_main_img_path, size_px=125, bg_hex=BG_VINOTINTO_DARK, border_width=3
            )

        tk.Label(header, image=self._menu_dino_photo, bg=BG_VINOTINTO_DARK).pack(pady=(0, 10))

        tk.Label(
            header,
            text="GUÍA DE CONTROLES DEL SISTEMA",
            font=("Segoe UI", 19, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_VINOTINTO_DARK
        ).pack()

        tk.Label(
            header,
            text="Selecciona la modalidad cuyos controles deseas consultar:",
            font=("Segoe UI", 10),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_DARK
        ).pack(pady=(4, 0))

        sub_panel = tk.Frame(
            frame,
            bg=BG_VINOTINTO_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=2,
            padx=35,
            pady=28
        )
        sub_panel.pack(fill="x", padx=65, pady=16)

        self._create_menu_button(
            sub_panel,
            text="🖐️ + 👁️   Manos + Mirada",
            subtitle="Ver los 5 controles gestuales de la mano combinados con la mirada",
            command=self.show_controls_screen,
            primary=True
        ).pack(fill="x", pady=(0, 16))

        self._create_menu_button(
            sub_panel,
            text="👁️   Solo Mirada",
            subtitle="Ver los 5 controles del modo 100% ocular y gestos faciales",
            command=self.show_controls_gaze_only_screen,
            primary=True
        ).pack(fill="x", pady=(0, 4))

        btn_back = tk.Button(
            frame,
            text="←   Volver al Menú Principal",
            font=("Segoe UI", 11, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_BUTTON,
            activebackground=BG_BUTTON_HOVER,
            activeforeground=TEXT_PRIMARY,
            padx=22,
            pady=8,
            bd=0,
            cursor="hand2",
            command=self.show_main_menu
        )
        btn_back.pack(pady=(12, 0))

    def show_controls_screen(self):
        """Controles de la modalidad 'Manos + Mirada' con las imágenes circulares del Dino."""
        self._clear_container()
        self._control_photos.clear()

        frame = tk.Frame(self.main_container, bg=BG_VINOTINTO_DARK)
        frame.pack(fill="both", expand=True, padx=36, pady=16)

        tk.Label(
            frame,
            text="✋  CONTROLES: MANOS + MIRADA",
            font=("Segoe UI", 17, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_VINOTINTO_DARK
        ).pack(pady=(0, 2))

        tk.Label(
            frame,
            text="Mueve el cursor con tu mirada y ejecuta las acciones con estos gestos de la mano:",
            font=("Segoe UI", 9),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_DARK
        ).pack(pady=(0, 8))

        list_panel = tk.Frame(
            frame,
            bg=BG_VINOTINTO_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=2,
            padx=16,
            pady=10
        )
        list_panel.pack(fill="both", expand=True, padx=10)

        for img_file, title_txt, desc_txt in self.control_items_data:
            img_path = self._resolve_dino_asset(img_file)
            photo = load_circular_dino_image(img_path, size_px=68, bg_hex=BG_VINOTINTO_CARD, border_width=2)
            self._control_photos.append(photo)

            row_card = tk.Frame(
                list_panel,
                bg=BG_VINOTINTO_CARD,
                highlightbackground=BORDER_COLOR,
                highlightthickness=1,
                padx=12,
                pady=5
            )
            row_card.pack(fill="x", pady=4)

            lbl_icon = tk.Label(row_card, image=photo, bg=BG_VINOTINTO_CARD, bd=0)
            lbl_icon.pack(side="left", padx=(4, 14))

            txt_col = tk.Frame(row_card, bg=BG_VINOTINTO_CARD)
            txt_col.pack(side="left", fill="both", expand=True)

            tk.Label(
                txt_col,
                text=f"•  {title_txt}",
                font=("Segoe UI", 12, "bold"),
                fg=BG_ACCENT_GOLD,
                bg=BG_VINOTINTO_CARD,
                anchor="w"
            ).pack(fill="x", pady=(2, 1))

            tk.Label(
                txt_col,
                text=desc_txt,
                font=("Segoe UI", 9),
                fg=TEXT_SECONDARY,
                bg=BG_VINOTINTO_CARD,
                anchor="w"
            ).pack(fill="x")

        btn_back = tk.Button(
            frame,
            text="←   Volver a Selección de Controles",
            font=("Segoe UI", 11, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_BUTTON,
            activebackground=BG_BUTTON_HOVER,
            activeforeground=TEXT_PRIMARY,
            padx=22,
            pady=7,
            bd=0,
            cursor="hand2",
            command=self.show_controls_mode_submenu
        )
        btn_back.pack(pady=(10, 2))

    def show_controls_gaze_only_screen(self):
        """Controles de la modalidad 'Solo Mirada' con las imágenes circulares del Dino."""
        self._clear_container()
        self._control_photos.clear()

        frame = tk.Frame(self.main_container, bg=BG_VINOTINTO_DARK)
        frame.pack(fill="both", expand=True, padx=36, pady=16)

        tk.Label(
            frame,
            text="👁️  CONTROLES: SOLO MIRADA",
            font=("Segoe UI", 17, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_VINOTINTO_DARK
        ).pack(pady=(0, 2))

        tk.Label(
            frame,
            text="Mueve el cursor con tu mirada y ejecuta todas las acciones con gestos de ojos y boca:",
            font=("Segoe UI", 9),
            fg=TEXT_SECONDARY,
            bg=BG_VINOTINTO_DARK
        ).pack(pady=(0, 8))

        list_panel = tk.Frame(
            frame,
            bg=BG_VINOTINTO_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=2,
            padx=16,
            pady=10
        )
        list_panel.pack(fill="both", expand=True, padx=10)

        for img_file, title_txt, desc_txt in self.gaze_control_items_data:
            img_path = self._resolve_dino_asset(img_file)
            photo = load_circular_dino_image(img_path, size_px=68, bg_hex=BG_VINOTINTO_CARD, border_width=2)
            self._control_photos.append(photo)

            row_card = tk.Frame(
                list_panel,
                bg=BG_VINOTINTO_CARD,
                highlightbackground=BORDER_COLOR,
                highlightthickness=1,
                padx=12,
                pady=5
            )
            row_card.pack(fill="x", pady=4)

            lbl_icon = tk.Label(row_card, image=photo, bg=BG_VINOTINTO_CARD, bd=0)
            lbl_icon.pack(side="left", padx=(4, 14))

            txt_col = tk.Frame(row_card, bg=BG_VINOTINTO_CARD)
            txt_col.pack(side="left", fill="both", expand=True)

            tk.Label(
                txt_col,
                text=f"•  {title_txt}",
                font=("Segoe UI", 12, "bold"),
                fg=BG_ACCENT_GOLD,
                bg=BG_VINOTINTO_CARD,
                anchor="w"
            ).pack(fill="x", pady=(2, 1))

            tk.Label(
                txt_col,
                text=desc_txt,
                font=("Segoe UI", 9),
                fg=TEXT_SECONDARY,
                bg=BG_VINOTINTO_CARD,
                anchor="w"
            ).pack(fill="x")

        btn_back = tk.Button(
            frame,
            text="←   Volver a Selección de Controles",
            font=("Segoe UI", 11, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_BUTTON,
            activebackground=BG_BUTTON_HOVER,
            activeforeground=TEXT_PRIMARY,
            padx=22,
            pady=7,
            bd=0,
            cursor="hand2",
            command=self.show_controls_mode_submenu
        )
        btn_back.pack(pady=(10, 2))

    # =========================================================================
    # ACCIONES DE SALIDA E INICIO
    # =========================================================================
    def _start_with_mode(self, mode_name):
        self.selected_mode = mode_name
        self.start_requested = True
        self._loading_active = False
        self.video_player.release()
        self.music.stop()
        self.root.destroy()

    def _on_close(self):
        self.start_requested = False
        self._loading_active = False
        self.video_player.release()
        self.music.stop()
        self.root.destroy()

    def run(self):
        """Ejecuta la pantalla de carga + menú y retorna (start_requested, selected_mode, sensitivity)."""
        self.show_loading_screen()
        self.root.mainloop()
        return self.start_requested, self.selected_mode, self.sensitivity


def launch_menu(initial_sensitivity=1.3):
    """Función auxiliar para abrir el menú desde main.py."""
    app = DinoMenuApp(initial_sensitivity=initial_sensitivity)
    return app.run()


if __name__ == "__main__":
    started, mode, sens = launch_menu()
    print(f"Menú finalizado -> Empezar={started}, Modo={mode}, Sensibilidad={sens}")
