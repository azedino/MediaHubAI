"""Universal downloader powered by yt-dlp."""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

try:
    from imageio_ffmpeg import get_ffmpeg_exe
except ImportError:
    get_ffmpeg_exe = None

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from core.errors import ClipForgeError, JobCancelledError
from core.models import MediaType

from .base import Downloader
from .cookies import CookieManager

DownloadProgress = Callable[[float, str], None]


class UniversalDownloader(Downloader):
    platform_name = "midia"

    def __init__(self, *, cookie_manager: CookieManager | None = None) -> None:
        super().__init__()
        self.cookie_manager = cookie_manager or CookieManager()

    def get_ydl_opts(self, url: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "extractor_retries": 5,
            "retries": 10,
            "fragment_retries": 10,
            "http_chunk_size": 10_485_760,
            "sleep_interval_requests": 1,
            "sleep_interval_subtitles": 1,
            "socket_timeout": 30,
            "geo_bypass": True,
        }
        cookie_selection = self.cookie_manager.get_cookiefile(url)
        if cookie_selection:
            options["cookiefile"] = str(cookie_selection.path)
        return options

    def download(
        self,
        url: str,
        destination: str | Path,
        selected_format: str = "Video",
        quality: str = "Best",
        file_ext: str = "mp4",
        output_template: str | None = None,
        progress_callback: Callable | None = None,
        *,
        media_type: MediaType | str | None = None,
        filename: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        if not url.lower().startswith(("http://", "https://")):
            raise ClipForgeError("Informe um link HTTP ou HTTPS valido.")

        output_dir = Path(destination).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        requested_type = self._resolve_media_type(media_type, selected_format)
        extension = file_ext.lower().lstrip(".")
        start_time = time.time()
        final_paths: list[str] = []

        if output_template:
            template = output_template
        elif filename:
            safe_name = self._safe_filename(filename)
            template = str(output_dir / f"{safe_name}.%(ext)s")
        else:
            template = str(output_dir / "%(title).180B [%(id)s].%(ext)s")

        def emit(value: float, status: str) -> None:
            if not progress_callback:
                return
            try:
                progress_callback(value, status)
            except TypeError:
                progress_callback(value)

        def progress_hook(data: dict) -> None:
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError("Download cancelado.")
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes", 0)
                if total:
                    emit(min(0.98, downloaded / total), "Baixando")
            elif status == "finished":
                if data.get("filename"):
                    final_paths.append(data["filename"])
                emit(0.99, "Finalizando arquivo")

        def postprocessor_hook(data: dict) -> None:
            if data.get("status") == "finished":
                info = data.get("info_dict") or {}
                filepath = info.get("filepath") or info.get("_filename")
                if filepath:
                    final_paths.append(filepath)

        yt_dlp_options = self.get_ydl_opts(url)
        yt_dlp_options.update(
            self._build_options(
                requested_type,
                quality,
                extension,
                template,
                progress_hook,
                postprocessor_hook,
            )
        )

        try:
            with YoutubeDL(cast(Any, yt_dlp_options)) as ydl:
                info = ydl.extract_info(url, download=True)
                prepared = ydl.prepare_filename(info)
        except JobCancelledError:
            raise
        except DownloadError as exc:
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError("Download cancelado.") from exc
            raise ClipForgeError(self._friendly_error(str(exc))) from exc
        except Exception as exc:
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError("Download cancelado.") from exc
            raise ClipForgeError(f"Falha ao baixar {self.platform_name}: {exc}") from exc

        candidates = [Path(value) for value in final_paths]
        candidates.append(Path(prepared))
        for candidate in reversed(candidates):
            if candidate.is_file() and candidate.suffix != ".part":
                self.last_output = str(candidate.resolve())
                emit(1.0, "Download concluido")
                return Path(self.last_output)
            located = self._locate_from_prepared_path(candidate)
            if located:
                self.last_output = located
                emit(1.0, "Download concluido")
                return Path(located)

        recent = [
            path
            for path in output_dir.iterdir()
            if path.is_file() and path.suffix != ".part" and path.stat().st_mtime >= start_time - 2
        ]
        if not recent:
            raise ClipForgeError("O extrator terminou, mas o arquivo final nao foi localizado.")
        result = max(recent, key=lambda path: path.stat().st_mtime).resolve()
        self.last_output = str(result)
        emit(1.0, "Download concluido")
        return result

    def _build_options(
        self,
        media_type: MediaType,
        quality: str,
        extension: str,
        template: str,
        progress_hook: Callable,
        postprocessor_hook: Callable,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "outtmpl": template,
            "noplaylist": True,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "windowsfilenames": os.name == "nt",
            "quiet": True,
            "no_warnings": True,
            "concurrent_fragment_downloads": 4,
        }
        ffmpeg = Path(__file__).resolve().parents[1] / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if ffmpeg.is_file():
            options["ffmpeg_location"] = str(ffmpeg.parent)
        elif get_ffmpeg_exe is not None:
            try:
                imageio_path = Path(get_ffmpeg_exe())
                if imageio_path.is_file():
                    options["ffmpeg_location"] = str(imageio_path.parent)
            except Exception:
                pass

        if media_type is MediaType.AUDIO:
            codec = extension if extension in {"mp3", "wav", "m4a", "opus", "flac"} else "mp3"
            options.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": codec,
                            "preferredquality": "0",
                        }
                    ],
                }
            )
        elif media_type is MediaType.IMAGE:
            image_format = extension if extension in {"jpg", "jpeg", "png", "webp"} else "jpg"
            options.update(
                {
                    "skip_download": True,
                    "writethumbnail": True,
                    "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": image_format}],
                }
            )
        else:
            max_height = self._quality_height(quality)
            height_filter = f"[height<={max_height}]" if max_height else ""
            options["format"] = f"bv*{height_filter}+ba/b{height_filter}/b"
            container = extension if extension in {"mp4", "webm", "mov", "mkv"} else "mp4"
            options["merge_output_format"] = container
        return options

    @staticmethod
    def _resolve_media_type(media_type: MediaType | str | None, selected_format: str) -> MediaType:
        if isinstance(media_type, MediaType):
            return media_type
        if media_type:
            return MediaType(str(media_type).lower())
        normalized = selected_format.lower()
        if "audio" in normalized or "udio" in normalized:
            return MediaType.AUDIO
        if "imagem" in normalized or "image" in normalized:
            return MediaType.IMAGE
        return MediaType.VIDEO

    @staticmethod
    def _quality_height(quality: str) -> int | None:
        match = re.search(r"(\d{3,4})", quality)
        return int(match.group(1)) if match else None

    @staticmethod
    def _safe_filename(value: str) -> str:
        safe = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "-", value).strip(" .-")
        return safe[:120] or "media"

    @staticmethod
    def _friendly_error(message: str) -> str:
        lowered = message.lower()
        auth_markers = (
            "private",
            "login",
            "cookies",
            "sign in",
            "authentication",
            "age-restricted",
            "sensitive",
            "members-only",
            "not available",
        )
        if any(marker in lowered for marker in auth_markers):
            return (
                "A midia exige autenticacao, contem restricao ou a sessao expirou. "
                "Atualize os cookies da plataforma em cookies/<plataforma>.txt ou .json e tente novamente."
            )
        if "unsupported url" in lowered:
            return "Este link ainda nao e suportado pelo extrator instalado. Atualize o yt-dlp."
        return f"Nao foi possivel baixar a midia: {message}"
