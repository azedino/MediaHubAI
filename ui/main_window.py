"""Janela principal do ClipForge Local."""

from __future__ import annotations

import os
import platform
import queue
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from CTkMessagebox import CTkMessagebox

from core.errors import JobCancelledError
from core.models import (
    CaptionPreset,
    ExportPreset,
    FilterPreset,
    MediaType,
    ShortsRequest,
    ShortsResult,
    ShortTemplate,
)
from downloaders import UniversalDownloader
from services import ShortCreationService
from ui.themes import COLORS

PRESET_LABELS = {preset.display_name: preset for preset in ExportPreset}
TEMPLATE_LABELS = {
    "Automático (detecta reação)": ShortTemplate.AUTO,
    "Preencher a tela": ShortTemplate.FILL,
    "Fundo desfocado": ShortTemplate.BLUR_BACKGROUND,
    "Reação no topo": ShortTemplate.REACTION_TOP,
    "Reação embaixo": ShortTemplate.REACTION_BOTTOM,
    "Tela dividida": ShortTemplate.SPLIT,
}
FILTER_LABELS = {
    "Vibrante": FilterPreset.VIBRANT,
    "Cinema": FilterPreset.CINEMATIC,
    "Quente": FilterPreset.WARM,
    "Frio": FilterPreset.COOL,
    "Preto e branco": FilterPreset.BLACK_AND_WHITE,
    "Sem filtro": FilterPreset.NONE,
}
CAPTION_LABELS = {
    "Viral (palavra destacada)": CaptionPreset.VIRAL,
    "Clean": CaptionPreset.CLEAN,
    "Neon": CaptionPreset.NEON,
    "Minimalista": CaptionPreset.MINIMAL,
}
LANGUAGE_LABELS = {"Detectar automaticamente": None, "Português": "pt", "English": "en", "Español": "es"}


class MediaHubApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ClipForge Local — estúdio de shorts")
        self.geometry("1220x820")
        self.minsize(1080, 720)
        self.configure(fg_color=COLORS["app_bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.last_downloaded_path: Path | None = None
        self.last_output_dir: Path | None = None
        self._busy = False
        self._closing = False
        self._ui_queue: queue.Queue[tuple[Callable, tuple]] = queue.Queue()
        self._cancel_event = threading.Event()
        self._short_service: ShortCreationService | None = None
        self._current_downloader: UniversalDownloader | None = None

        self._build_shell()
        self.show_page("download")
        self.after(40, self._drain_ui_queue)

    def _build_shell(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=238, corner_radius=0, fg_color=COLORS["sidebar"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        brand = ctk.CTkLabel(
            self.sidebar,
            text="CLIPFORGE",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["primary"],
        )
        brand.pack(anchor="w", padx=24, pady=(30, 0))
        ctk.CTkLabel(
            self.sidebar,
            text="LOCAL  •  AI VIDEO STUDIO",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=24, pady=(0, 30))

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for key, label in (
            ("download", "↓   Baixar mídia"),
            ("studio", "✦   Criar Shorts"),
            ("about", "ⓘ   Privacidade e uso"),
        ):
            button = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                height=46,
                corner_radius=10,
                fg_color="transparent",
                hover_color=COLORS["card_hover"],
                text_color=COLORS["text"],
                font=ctk.CTkFont(size=14, weight="bold"),
                command=lambda page=key: self.show_page(page),
            )
            button.pack(fill="x", padx=16, pady=5)
            self.nav_buttons[key] = button

        self.appearance_switch = ctk.CTkSwitch(
            self.sidebar,
            text="Tema escuro",
            command=self._toggle_appearance,
            progress_color=COLORS["primary"],
        )
        self.appearance_switch.select()
        self.appearance_switch.pack(side="bottom", anchor="w", padx=24, pady=25)

        self.workspace = ctk.CTkFrame(self, corner_radius=0, fg_color=COLORS["app_bg"])
        self.workspace.grid(row=0, column=1, sticky="nsew")
        self.workspace.grid_rowconfigure(0, weight=1)
        self.workspace.grid_columnconfigure(0, weight=1)

        # Pages are scrollable frames
        self.pages: dict[str, ctk.CTkScrollableFrame] = {}
        self.pages["download"] = self._build_download_page()
        self.pages["studio"] = self._build_studio_page()
        self.pages["about"] = self._build_about_page()

    def _page(self) -> ctk.CTkScrollableFrame:
        page = ctk.CTkScrollableFrame(
            self.workspace,
            corner_radius=0,
            fg_color=COLORS["app_bg"],
            scrollbar_button_color=COLORS["border"],
        )
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        return page

    @staticmethod
    def _section_title(parent, title: str, subtitle: str, row: int) -> None:
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=row, column=0, sticky="w", padx=34, pady=(28, 0))
        ctk.CTkLabel(
            parent,
            text=subtitle,
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
        ).grid(row=row + 1, column=0, sticky="w", padx=34, pady=(2, 18))

    @staticmethod
    def _card(parent, row: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            corner_radius=16,
            fg_color=COLORS["card"],
            border_width=1,
            border_color=COLORS["border"],
        )
        card.grid(row=row, column=0, sticky="ew", padx=34, pady=(0, 18))
        card.grid_columnconfigure(0, weight=1)
        return card

    def _build_download_page(self) -> ctk.CTkScrollableFrame:
        page = self._page()
        self._section_title(
            page,
            "Baixar mídia",
            "Vídeos, áudios e imagens de links compatíveis com o yt-dlp.",
            0,
        )
        card = self._card(page, 2)

        ctk.CTkLabel(card, text="Link da mídia", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=22, pady=(20, 5)
        )
        self.download_url_entry = ctk.CTkEntry(
            card, height=42, placeholder_text="https://youtube.com/...  •  TikTok  •  Instagram  •  X"
        )
        self.download_url_entry.grid(row=1, column=0, sticky="ew", padx=22)

        self.download_type_control = ctk.CTkSegmentedButton(
            card,
            values=["Vídeo", "Áudio", "Imagem"],
            command=self._on_download_type,
            selected_color=COLORS["primary"],
            selected_hover_color=COLORS["primary_hover"],
        )
        self.download_type_control.set("Vídeo")
        self.download_type_control.grid(row=2, column=0, sticky="ew", padx=22, pady=16)

        options = ctk.CTkFrame(card, fg_color="transparent")
        options.grid(row=3, column=0, sticky="ew", padx=22)
        options.grid_columnconfigure(0, weight=1)
        options.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(options, text="Qualidade", anchor="w").grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(options, text="Formato", anchor="w").grid(row=0, column=1, sticky="ew", padx=(12, 0))
        self.download_quality = ctk.CTkComboBox(
            options, values=["Melhor", "1080p", "720p", "480p", "360p"], height=38
        )
        self.download_quality.set("1080p")
        self.download_quality.grid(row=1, column=0, sticky="ew")
        self.download_format = ctk.CTkComboBox(options, values=["MP4", "WEBM", "MOV"], height=38)
        self.download_format.set("MP4")
        self.download_format.grid(row=1, column=1, sticky="ew", padx=(12, 0))

        ctk.CTkLabel(card, text="Nome personalizado (opcional)", anchor="w").grid(
            row=4, column=0, sticky="ew", padx=22, pady=(16, 5)
        )
        self.download_filename = ctk.CTkEntry(
            card, height=38, placeholder_text="Se vazio, usa o título original"
        )
        self.download_filename.grid(row=5, column=0, sticky="ew", padx=22)

        ctk.CTkLabel(card, text="Pasta de destino", anchor="w").grid(
            row=6, column=0, sticky="ew", padx=22, pady=(16, 5)
        )
        destination_row = ctk.CTkFrame(card, fg_color="transparent")
        destination_row.grid(row=7, column=0, sticky="ew", padx=22)
        destination_row.grid_columnconfigure(0, weight=1)
        self.download_destination = ctk.CTkEntry(destination_row, height=38)
        self.download_destination.insert(0, str(Path.home() / "Downloads"))
        self.download_destination.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            destination_row,
            text="Escolher",
            width=100,
            height=38,
            fg_color=COLORS["secondary"],
            command=lambda: self._choose_directory(self.download_destination),
        ).grid(row=0, column=1, padx=(10, 0))

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=8, column=0, sticky="ew", padx=22, pady=(20, 8))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        self.download_button = ctk.CTkButton(
            buttons,
            text="BAIXAR AGORA",
            height=44,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self.start_download,
        )
        self.download_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            buttons,
            text="Abrir último arquivo",
            height=44,
            fg_color=COLORS["secondary"],
            command=self.open_last_downloaded,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.download_progress = ctk.CTkProgressBar(card, progress_color=COLORS["primary"])
        self.download_progress.set(0)
        self.download_progress.grid(row=9, column=0, sticky="ew", padx=22, pady=(8, 5))
        self.download_status = ctk.CTkLabel(
            card, text="Pronto para baixar", anchor="w", text_color=COLORS["muted"]
        )
        self.download_status.grid(row=10, column=0, sticky="ew", padx=22, pady=(0, 18))

        note = self._card(page, 3)
        ctk.CTkLabel(
            note,
            text=(
                "Use somente conteúdo próprio, autorizado ou permitido pela lei e pelos termos da plataforma."
            ),
            wraplength=760,
            justify="left",
            text_color=COLORS["muted"],
        ).grid(row=0, column=0, sticky="w", padx=20, pady=16)
        return page

    def _build_studio_page(self) -> ctk.CTkScrollableFrame:
        page = self._page()
        self._section_title(
            page,
            "Criar Shorts",
            "IA local para cortes, legendas, reação, reenquadramento e acabamento.",
            0,
        )

        source_card = self._card(page, 2)
        ctk.CTkLabel(source_card, text="Link ou arquivo de vídeo", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=22, pady=(20, 5)
        )
        source_row = ctk.CTkFrame(source_card, fg_color="transparent")
        source_row.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 18))
        source_row.grid_columnconfigure(0, weight=1)
        self.studio_source = ctk.CTkEntry(
            source_row, height=42, placeholder_text="Cole um link ou selecione um vídeo local"
        )
        self.studio_source.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            source_row,
            text="Arquivo",
            width=90,
            height=42,
            fg_color=COLORS["secondary"],
            command=self._choose_video,
        ).grid(row=0, column=1, padx=(10, 0))

        config_card = self._card(page, 3)
        config_card.grid_columnconfigure(0, weight=1)
        config_card.grid_columnconfigure(1, weight=1)
        self.studio_controls: dict[str, object] = {}

        left = ctk.CTkFrame(config_card, fg_color="transparent")
        right = ctk.CTkFrame(config_card, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(22, 10), pady=18)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 22), pady=18)
        left.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._label(left, "Destino / proporção", 0)
        self.preset_combo = ctk.CTkComboBox(left, values=list(PRESET_LABELS), height=38)
        self.preset_combo.set(ExportPreset.YOUTUBE_SHORTS.display_name)
        self.preset_combo.grid(row=1, column=0, sticky="ew")

        self._label(left, "Template de enquadramento", 2)
        self.template_combo = ctk.CTkComboBox(left, values=list(TEMPLATE_LABELS), height=38)
        self.template_combo.set("Automático (detecta reação)")
        self.template_combo.grid(row=3, column=0, sticky="ew")

        self._label(left, "Filtro", 4)
        self.filter_combo = ctk.CTkComboBox(left, values=list(FILTER_LABELS), height=38)
        self.filter_combo.set("Vibrante")
        self.filter_combo.grid(row=5, column=0, sticky="ew")

        number_row = ctk.CTkFrame(left, fg_color="transparent")
        number_row.grid(row=6, column=0, sticky="ew", pady=(14, 0))
        number_row.grid_columnconfigure(0, weight=1)
        number_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(number_row, text="Quantidade", anchor="w").grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(number_row, text="Modelo da IA", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=(10, 0)
        )
        self.clips_combo = ctk.CTkComboBox(number_row, values=["1", "2", "3", "5"], height=38)
        self.clips_combo.set("3")
        self.clips_combo.grid(row=1, column=0, sticky="ew")
        self.model_combo = ctk.CTkComboBox(number_row, values=["tiny", "base", "small", "medium"], height=38)
        self.model_combo.set("small")
        self.model_combo.grid(row=1, column=1, sticky="ew", padx=(10, 0))

        self.duration_label = ctk.CTkLabel(right, text="Duração final • 30s", anchor="w")
        self.duration_label.grid(row=0, column=0, sticky="ew")
        self.duration_slider = ctk.CTkSlider(
            right,
            from_=10,
            to=90,
            number_of_steps=16,
            progress_color=COLORS["primary"],
            command=lambda value: self.duration_label.configure(text=f"Duração final • {round(value):d}s"),
        )
        self.duration_slider.set(30)
        self.duration_slider.grid(row=1, column=0, sticky="ew", pady=(4, 8))

        self.speed_label = ctk.CTkLabel(right, text="Velocidade • 1.00x", anchor="w")
        self.speed_label.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.speed_slider = ctk.CTkSlider(
            right,
            from_=5,
            to=20,
            number_of_steps=30,
            progress_color=COLORS["primary"],
            command=lambda value: self.speed_label.configure(text=f"Velocidade • {value / 10:.2f}x"),
        )
        self.speed_slider.set(10)
        self.speed_slider.grid(row=3, column=0, sticky="ew", pady=(4, 8))

        self._label(right, "Idioma da fala", 4)
        self.language_combo = ctk.CTkComboBox(right, values=list(LANGUAGE_LABELS), height=38)
        self.language_combo.set("Detectar automaticamente")
        self.language_combo.grid(row=5, column=0, sticky="ew")

        self.caption_var = ctk.BooleanVar(value=True)
        self.mirror_var = ctk.BooleanVar(value=False)
        switches = ctk.CTkFrame(right, fg_color="transparent")
        switches.grid(row=6, column=0, sticky="ew", pady=(17, 4))
        switches.grid_columnconfigure(0, weight=1)
        switches.grid_columnconfigure(1, weight=1)
        ctk.CTkSwitch(
            switches,
            text="Legendas automáticas",
            variable=self.caption_var,
            progress_color=COLORS["primary"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkSwitch(
            switches,
            text="Espelhar vídeo",
            variable=self.mirror_var,
            progress_color=COLORS["primary"],
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        caption_row = ctk.CTkFrame(config_card, fg_color="transparent")
        caption_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=22, pady=(0, 18))
        caption_row.grid_columnconfigure(0, weight=1)
        caption_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(caption_row, text="Estilo da legenda", anchor="w").grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(caption_row, text="Fonte", anchor="w").grid(row=0, column=1, sticky="ew", padx=(12, 0))
        self.caption_combo = ctk.CTkComboBox(caption_row, values=list(CAPTION_LABELS), height=38)
        self.caption_combo.set("Viral (palavra destacada)")
        self.caption_combo.grid(row=1, column=0, sticky="ew")
        self.font_combo = ctk.CTkComboBox(
            caption_row,
            values=["Arial", "Impact", "Montserrat", "Poppins", "Segoe UI"],
            height=38,
        )
        self.font_combo.set("Arial")
        self.font_combo.grid(row=1, column=1, sticky="ew", padx=(12, 0))

        output_card = self._card(page, 4)
        ctk.CTkLabel(output_card, text="Pasta dos shorts", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=22, pady=(18, 5)
        )
        output_row = ctk.CTkFrame(output_card, fg_color="transparent")
        output_row.grid(row=1, column=0, sticky="ew", padx=22)
        output_row.grid_columnconfigure(0, weight=1)
        self.studio_destination = ctk.CTkEntry(output_row, height=38)
        self.studio_destination.insert(0, str(Path.home() / "Videos" / "ClipForge"))
        self.studio_destination.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            output_row,
            text="Escolher",
            width=100,
            height=38,
            fg_color=COLORS["secondary"],
            command=lambda: self._choose_directory(self.studio_destination),
        ).grid(row=0, column=1, padx=(10, 0))

        action_row = ctk.CTkFrame(output_card, fg_color="transparent")
        action_row.grid(row=2, column=0, sticky="ew", padx=22, pady=(18, 10))
        action_row.grid_columnconfigure(0, weight=1)
        self.generate_button = ctk.CTkButton(
            action_row,
            text="✦  ANALISAR E CRIAR SHORTS",
            height=48,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.start_short_creation,
        )
        self.generate_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.cancel_button = ctk.CTkButton(
            action_row,
            text="Cancelar",
            width=110,
            height=48,
            state="disabled",
            fg_color=COLORS["danger"],
            hover_color="#a93444",
            command=self.cancel_current_job,
        )
        self.cancel_button.grid(row=0, column=1)

        self.studio_progress = ctk.CTkProgressBar(output_card, progress_color=COLORS["primary"])
        self.studio_progress.set(0)
        self.studio_progress.grid(row=3, column=0, sticky="ew", padx=22, pady=(4, 5))
        self.studio_status = ctk.CTkLabel(
            output_card,
            text="Tudo pronto. O processamento acontece localmente.",
            anchor="w",
            text_color=COLORS["muted"],
        )
        self.studio_status.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 10))
        self.result_text = ctk.CTkTextbox(output_card, height=130, activate_scrollbars=True)
        self.result_text.grid(row=5, column=0, sticky="ew", padx=22, pady=(0, 10))
        self.result_text.insert("1.0", "Os arquivos criados e os motivos dos cortes aparecerão aqui.")
        self.result_text.configure(state="disabled")
        ctk.CTkButton(
            output_card,
            text="Abrir pasta de saída",
            height=38,
            fg_color=COLORS["secondary"],
            command=self.open_output_directory,
        ).grid(row=6, column=0, sticky="e", padx=22, pady=(0, 18))
        return page

    def _build_about_page(self) -> ctk.CTkScrollableFrame:
        page = self._page()
        self._section_title(
            page,
            "Privacidade e uso responsável",
            "O diferencial local também precisa ser um diferencial ético.",
            0,
        )
        card = self._card(page, 2)
        text = (
            "PROCESSAMENTO LOCAL\n\n"
            "Transcrição, análise dos cortes, detecção de rostos e renderização são executadas no seu PC. "
            "Na primeira utilização, o faster-whisper pode baixar o modelo escolhido.\n\n"
            "DIREITOS AUTORAIS\n\n"
            "Baixe e edite somente conteúdo próprio, licenciado, em domínio público "
            "ou usado com autorização. Este aplicativo não remove DRM, não burla "
            "conteúdo privado e não garante permissão de publicação.\n\n"
            "SCORE DE POTENCIAL\n\n"
            "O score combina ganchos linguísticos, perguntas, emoção, ritmo de fala e mudanças de cena. "
            "É um auxílio editorial explicável — não uma promessa de alcance ou renda."
        )
        ctk.CTkLabel(
            card,
            text=text,
            justify="left",
            anchor="w",
            wraplength=780,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=14),
        ).grid(row=0, column=0, sticky="ew", padx=24, pady=24)
        return page

    @staticmethod
    def _label(parent, text: str, row: int) -> None:
        ctk.CTkLabel(parent, text=text, anchor="w").grid(
            row=row, column=0, sticky="ew", pady=(12 if row else 0, 4)
        )

    def show_page(self, page_key: str) -> None:
        for key, page in self.pages.items():
            if key == page_key:
                page.grid()
            else:
                page.grid_remove()
            self.nav_buttons[key].configure(
                fg_color=COLORS["primary_soft"] if key == page_key else "transparent",
                text_color=COLORS["primary"] if key == page_key else COLORS["text"],
            )

    def _on_download_type(self, selected: str) -> None:
        if selected == "Áudio":
            self.download_format.configure(values=["MP3", "WAV", "M4A", "FLAC"])
            self.download_format.set("MP3")
            self.download_quality.configure(state="disabled")
        elif selected == "Imagem":
            self.download_format.configure(values=["JPG", "PNG", "WEBP"])
            self.download_format.set("JPG")
            self.download_quality.configure(state="disabled")
        else:
            self.download_format.configure(values=["MP4", "WEBM", "MOV"])
            self.download_format.set("MP4")
            self.download_quality.configure(state="normal")

    def start_download(self) -> None:
        url = self.download_url_entry.get().strip()
        destination_text = self.download_destination.get().strip()
        if not url or not destination_text:
            self._message("Dados incompletos", "Informe o link e a pasta de destino.", "warning")
            return
        destination = Path(destination_text).expanduser()
        selected_format = self.download_type_control.get()
        quality = self.download_quality.get()
        extension = self.download_format.get().lower()
        filename = self.download_filename.get().strip() or None
        media_type = {"Vídeo": MediaType.VIDEO, "Áudio": MediaType.AUDIO, "Imagem": MediaType.IMAGE}[
            selected_format
        ]
        self.download_progress.set(0)
        self.download_status.configure(text="Preparando download...")

        def job() -> Path:
            self._current_downloader = UniversalDownloader()
            return self._current_downloader.download(
                url=url,
                destination=destination,
                media_type=media_type,
                selected_format=selected_format,
                quality=quality,
                file_ext=extension,
                filename=filename,
                cancel_event=self._cancel_event,
                progress_callback=lambda value, status: self._dispatch(
                    self._update_download_progress, value, status
                ),
            )

        self._run_job(job, self._download_finished)

    def _download_finished(self, output: Path) -> None:
        self.last_downloaded_path = output
        self.download_progress.set(1)
        self.download_status.configure(text=f"Salvo em: {output}")
        if output.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
            self._set_entry(self.studio_source, str(output))

    def _update_download_progress(self, value: float, status: str) -> None:
        self.download_progress.set(value)
        self.download_status.configure(text=f"{status} • {round(value * 100)}%")

    def start_short_creation(self) -> None:
        source_text = self.studio_source.get().strip()
        destination_text = self.studio_destination.get().strip()
        if not source_text or not destination_text:
            self._message("Dados incompletos", "Informe um link/arquivo e a pasta de saída.", "warning")
            return
        destination = Path(destination_text).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        self.last_output_dir = destination
        preset = PRESET_LABELS[self.preset_combo.get()]
        clips_count = int(self.clips_combo.get())
        target_duration = round(self.duration_slider.get())
        speed = round(self.speed_slider.get(), 2)
        mirror = self.mirror_var.get()
        filter_preset = FILTER_LABELS[self.filter_combo.get()]
        template = TEMPLATE_LABELS[self.template_combo.get()]
        captions_enabled = self.caption_var.get()
        caption_preset = CAPTION_LABELS[self.caption_combo.get()]
        caption_font = self.font_combo.get()
        language = LANGUAGE_LABELS[self.language_combo.get()]
        whisper_model = self.model_combo.get()
        self.studio_progress.set(0)
        self.studio_status.configure(text="Preparando o estúdio...")
        self._set_result_text("Análise iniciada. O tempo depende da duração do vídeo e do modelo de IA.\n")

        def job() -> ShortsResult:
            source = self._resolve_studio_source(source_text, destination)
            request = ShortsRequest(
                source=source,
                output_dir=destination,
                preset=preset,
                clips_count=clips_count,
                target_duration=target_duration,
                speed=speed,
                mirror=mirror,
                filter_preset=filter_preset,
                template=template,
                captions_enabled=captions_enabled,
                caption_preset=caption_preset,
                caption_font=caption_font,
                language=language,
                whisper_model=whisper_model,
            )
            self._short_service = ShortCreationService()
            return self._short_service.create(
                request,
                cancel_event=self._cancel_event,
                progress_callback=lambda value, status: self._dispatch(
                    self._update_studio_progress,
                    0.20 + value * 0.80 if self._is_url(source_text) else value,
                    status,
                ),
            )

        self._run_job(job, self._shorts_finished)

    def _resolve_studio_source(self, source_text: str, destination: Path) -> Path:
        if not self._is_url(source_text):
            return Path(source_text).expanduser().resolve()
        source_dir = destination / "fontes"
        source_dir.mkdir(parents=True, exist_ok=True)
        self._current_downloader = UniversalDownloader()
        output = self._current_downloader.download(
            url=source_text,
            destination=source_dir,
            media_type=MediaType.VIDEO,
            quality="1080p",
            file_ext="mp4",
            cancel_event=self._cancel_event,
            progress_callback=lambda value, status: self._dispatch(
                self._update_studio_progress, value * 0.20, f"Fonte: {status}"
            ),
        )
        self.last_downloaded_path = output
        return output

    def _shorts_finished(self, result: ShortsResult) -> None:
        self.studio_progress.set(1)
        reaction = (
            f"Reação detectada ({result.reaction.confidence:.0%})."
            if result.reaction.detected
            else "Câmera de reação não detectada."
        )
        lines = [f"Concluído: {len(result.outputs)} arquivo(s). {reaction}", ""]
        for candidate, output in zip(result.candidates, result.outputs, strict=True):
            reasons = ", ".join(candidate.reasons)
            lines.append(
                f"• Score {candidate.score:.0f} | {candidate.start:.1f}s–"
                f"{candidate.end:.1f}s | {reasons}\n  {output}"
            )
        if result.warnings:
            lines.extend(["", "Avisos:", *[f"• {warning}" for warning in result.warnings]])
        self._set_result_text("\n".join(lines))
        self.studio_status.configure(text=f"{len(result.outputs)} short(s) pronto(s) para revisão.")

    def _update_studio_progress(self, value: float, status: str) -> None:
        self.studio_progress.set(max(0, min(1, value)))
        self.studio_status.configure(text=f"{status} • {round(value * 100)}%")

    def _run_job(self, worker: Callable, on_success: Callable) -> None:
        if self._busy:
            self._message("Trabalho em andamento", "Cancele ou aguarde a tarefa atual.", "warning")
            return
        self._cancel_event.clear()
        self._set_busy(True)

        def runner() -> None:
            try:
                result = worker()
            except JobCancelledError as exc:
                self._dispatch(self._job_cancelled, str(exc))
            except Exception as exc:
                self._dispatch(self._job_failed, exc)
            else:
                self._dispatch(on_success, result)
            finally:
                self._dispatch(self._set_busy, False)

        threading.Thread(target=runner, name="clipforge-job", daemon=True).start()

    def cancel_current_job(self) -> None:
        if not self._busy:
            return
        self._cancel_event.set()
        if self._short_service:
            self._short_service.cancel()
        self.studio_status.configure(text="Cancelando com segurança...")
        self.download_status.configure(text="Cancelando...")

    def _job_cancelled(self, message: str) -> None:
        self.studio_status.configure(text=message or "Trabalho cancelado.")
        self.download_status.configure(text=message or "Trabalho cancelado.")

    def _job_failed(self, error: Exception) -> None:
        self.studio_status.configure(text="Falha no processamento.")
        self.download_status.configure(text="Falha no download.")
        self._message("Não foi possível concluir", str(error), "cancel")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.download_button.configure(state=state)
        self.generate_button.configure(state=state)
        self.cancel_button.configure(state="normal" if busy else "disabled")
        if not busy:
            self._current_downloader = None

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Escolha um vídeo",
            filetypes=[
                ("Vídeos", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if path:
            self._set_entry(self.studio_source, path)

    @staticmethod
    def _choose_directory(entry: ctk.CTkEntry) -> None:
        initial = entry.get().strip() or str(Path.home())
        directory = filedialog.askdirectory(initialdir=initial)
        if directory:
            entry.delete(0, "end")
            entry.insert(0, directory)

    def open_last_downloaded(self) -> None:
        if not self.last_downloaded_path or not self.last_downloaded_path.exists():
            self._message("Nenhum arquivo", "Faça um download primeiro.", "warning")
            return
        self._open_path(self.last_downloaded_path)

    def open_output_directory(self) -> None:
        directory = self.last_output_dir or Path(self.studio_destination.get()).expanduser()
        if not directory.exists():
            self._message("Pasta inexistente", "Crie um short primeiro.", "warning")
            return
        self._open_path(directory)

    @staticmethod
    def _open_path(path: Path) -> None:
        if platform.system() == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _toggle_appearance(self) -> None:
        ctk.set_appearance_mode("Dark" if self.appearance_switch.get() else "Light")

    def _dispatch(self, callback: Callable, *args) -> None:
        if self._closing:
            return
        if threading.current_thread() is threading.main_thread():
            callback(*args)
            return
        self._ui_queue.put((callback, args))

    def _drain_ui_queue(self) -> None:
        if self._closing:
            return
        while True:
            try:
                callback, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            callback(*args)
        self.after(40, self._drain_ui_queue)

    @staticmethod
    def _set_entry(entry: ctk.CTkEntry, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)

    def _set_result_text(self, value: str) -> None:
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", value)
        self.result_text.configure(state="disabled")

    @staticmethod
    def _is_url(value: str) -> bool:
        return value.lower().startswith(("http://", "https://"))

    @staticmethod
    def _message(title: str, message: str, icon: str = "info") -> None:
        CTkMessagebox(title=title, message=message, icon=icon)

    def _on_close(self) -> None:
        self._closing = True
        self._cancel_event.set()
        if self._short_service:
            self._short_service.cancel()
        self.destroy()
