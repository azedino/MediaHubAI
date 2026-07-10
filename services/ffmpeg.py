"""Invocação segura e observável do FFmpeg distribuído com o aplicativo."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Iterable

try:
    from imageio_ffmpeg import get_ffmpeg_exe
except ImportError:
    get_ffmpeg_exe = None
from dataclasses import dataclass
from pathlib import Path

from core.errors import DependencyUnavailableError, InvalidMediaError, JobCancelledError
from core.models import MediaInfo

from .hardware import HardwareSelector

ProgressCallback = Callable[[float, str], None]


def resolve_ffmpeg_executable(executable: str | Path | None = None) -> Path:
    candidates: list[Path | None] = []
    if executable:
        candidates.append(Path(executable))
    env_path = os.environ.get("CLIPFORGE_FFMPEG")
    if env_path:
        candidates.append(Path(env_path))
    project_binary = Path(__file__).resolve().parents[1] / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    candidates.append(project_binary)
    system_binary = shutil.which("ffmpeg")
    if system_binary:
        candidates.append(Path(system_binary))

    if get_ffmpeg_exe is not None:
        try:
            imageio_path = Path(get_ffmpeg_exe())
            candidates.append(imageio_path)
        except Exception:
            pass

    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    raise DependencyUnavailableError(
        "FFmpeg não encontrado. Instale o pacote imageio-ffmpeg ou defina a variável CLIPFORGE_FFMPEG."
    )


@dataclass(frozen=True, slots=True)
class EncoderProfile:
    name: str
    args: tuple[str, ...]
    vendor: str
    hardware: bool


class FFmpegService:
    _DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
    _VIDEO_RE = re.compile(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b")
    _FPS_RE = re.compile(r"(?<!tbr, )\b(\d+(?:\.\d+)?)\s*fps\b")
    _SCENE_TIME_RE = re.compile(r"pts_time:([0-9.]+)")

    def __init__(self, executable: str | Path | None = None) -> None:
        self.executable = self._resolve_executable(executable)
        self._process: subprocess.Popen[str] | None = None
        self._process_lock = threading.Lock()
        self._encoder_cache: dict[tuple[str, str], EncoderProfile] = {}

    @staticmethod
    def _resolve_executable(executable: str | Path | None) -> Path:
        return resolve_ffmpeg_executable(executable)

    @property
    def _creation_flags(self) -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    def probe(self, source: str | Path) -> MediaInfo:
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise InvalidMediaError(f"Mídia não encontrada: {path}")

        completed = subprocess.run(
            [str(self.executable), "-hide_banner", "-i", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=self._creation_flags,
            check=False,
        )
        output = completed.stdout or ""
        duration_match = self._DURATION_RE.search(output)
        video_match = self._VIDEO_RE.search(output)
        if not duration_match or not video_match:
            raise InvalidMediaError(
                "Não foi possível ler duração e resolução. Confirme se o arquivo é um vídeo válido."
            )

        hours, minutes, seconds = duration_match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        width, height = (int(value) for value in video_match.groups())
        return MediaInfo(
            path=path,
            duration=duration,
            width=width,
            height=height,
            has_audio="Audio:" in output,
            fps=self._parse_fps(output),
        )

    def select_h264_encoder(self, requested_device: str = "auto") -> EncoderProfile:
        """Select a usable H.264 encoder for CPU, NVIDIA, AMD, or Intel GPUs."""
        requested_device = os.environ.get(
            "CLIPFORGE_RENDER_DEVICE",
            requested_device or "auto",
        ).strip().lower()
        forced_encoder = os.environ.get("CLIPFORGE_FFMPEG_ENCODER", "").strip()
        gpu = HardwareSelector().preferred_gpu() if requested_device != "cpu" else None
        vendor = gpu.vendor if gpu else "cpu"
        cache_key = (requested_device, forced_encoder or vendor)
        cached = self._encoder_cache.get(cache_key)
        if cached:
            return cached

        try:
            completed = subprocess.run(
                [str(self.executable), "-hide_banner", "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._creation_flags,
                check=False,
            )
        except OSError:
            return self._software_encoder()
        output = completed.stdout or ""
        candidates = self._encoder_candidates(vendor, requested_device, forced_encoder)
        for profile in candidates:
            if profile.name not in output:
                continue
            if self._encoder_is_usable(profile):
                self._encoder_cache[cache_key] = profile
                return profile

        software = self._software_encoder()
        self._encoder_cache[cache_key] = software
        return software

    def detect_scene_changes(
        self,
        source: str | Path,
        *,
        threshold: float = 0.30,
        cancel_event: threading.Event | None = None,
    ) -> list[float]:
        """Detecta mudanças visuais em baixa resolução para reduzir custo de CPU."""
        filter_expression = f"fps=2,scale=320:-2,select='gt(scene,{threshold:.2f})',showinfo"
        command = [
            str(self.executable),
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(Path(source).resolve()),
            "-vf",
            filter_expression,
            "-an",
            "-f",
            "null",
            "-",
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=self._creation_flags,
        )
        times: list[float] = []
        assert process.stderr is not None
        for line in process.stderr:
            if cancel_event and cancel_event.is_set():
                process.terminate()
                raise JobCancelledError("Criação cancelada.")
            match = self._SCENE_TIME_RE.search(line)
            if match:
                value = float(match.group(1))
                if not times or value - times[-1] >= 0.35:
                    times.append(value)
                if len(times) >= 500:
                    process.terminate()
                    break
        process.wait()
        return times

    def run(
        self,
        arguments: Iterable[str | Path],
        *,
        expected_duration: float,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        args = [str(value) for value in arguments]
        if not args:
            raise ValueError("A lista de argumentos do FFmpeg está vazia.")

        output = args[-1]
        command = [
            str(self.executable),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *args[:-1],
            "-progress",
            "pipe:1",
            "-nostats",
            output,
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=self._creation_flags,
        )
        with self._process_lock:
            self._process = process

        tail: deque[str] = deque(maxlen=30)
        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.strip()
                if line:
                    tail.append(line)
                if cancel_event and cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise JobCancelledError("Criação cancelada.")

                if line.startswith("out_time_ms="):
                    try:
                        elapsed = int(line.partition("=")[2]) / 1_000_000
                    except ValueError:
                        continue
                    if progress_callback and expected_duration > 0:
                        progress_callback(min(1.0, elapsed / expected_duration), "Renderizando")

            return_code = process.wait()
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError("Criação cancelada.")
            if return_code != 0:
                details = "\n".join(tail) or "FFmpeg encerrou sem detalhes."
                raise InvalidMediaError(f"Falha ao renderizar o vídeo:\n{details}")
            if progress_callback:
                progress_callback(1.0, "Render concluído")
        finally:
            with self._process_lock:
                if self._process is process:
                    self._process = None

    def cancel(self) -> None:
        with self._process_lock:
            process = self._process
        if process and process.poll() is None:
            process.terminate()

    def _encoder_is_usable(self, profile: EncoderProfile) -> bool:
        if not profile.hardware:
            return True
        command = [
            str(self.executable),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=128x128:r=30:d=0.15",
            "-frames:v",
            "1",
            "-an",
            "-vf",
            "format=nv12",
            "-c:v",
            profile.name,
            *profile.args,
            "-f",
            "null",
            "-",
        ]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                creationflags=self._creation_flags,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0

    @staticmethod
    def _encoder_candidates(
        vendor: str,
        requested_device: str,
        forced_encoder: str,
    ) -> tuple[EncoderProfile, ...]:
        profiles = {
            "h264_nvenc": EncoderProfile(
                "h264_nvenc",
                ("-preset", "p4", "-cq", "20", "-b:v", "0"),
                "nvidia",
                True,
            ),
            "h264_amf": EncoderProfile(
                "h264_amf",
                ("-quality", "balanced", "-qp_i", "20", "-qp_p", "22"),
                "amd",
                True,
            ),
            "h264_qsv": EncoderProfile(
                "h264_qsv",
                ("-global_quality", "20", "-look_ahead", "0"),
                "intel",
                True,
            ),
        }
        if forced_encoder:
            forced = profiles.get(forced_encoder)
            if forced:
                return (forced, FFmpegService._software_encoder())
            if forced_encoder == "libx264":
                return (FFmpegService._software_encoder(),)

        if requested_device == "cpu":
            return (FFmpegService._software_encoder(),)

        by_vendor = {
            "nvidia": ("h264_nvenc", "h264_qsv", "h264_amf"),
            "amd": ("h264_amf", "h264_qsv", "h264_nvenc"),
            "intel": ("h264_qsv", "h264_amf", "h264_nvenc"),
            "cpu": (),
        }
        ordered = by_vendor.get(vendor, ("h264_amf", "h264_nvenc", "h264_qsv"))
        return tuple(profiles[name] for name in ordered) + (FFmpegService._software_encoder(),)

    @staticmethod
    def _software_encoder() -> EncoderProfile:
        return EncoderProfile("libx264", ("-preset", "veryfast", "-crf", "18"), "cpu", False)

    @classmethod
    def _parse_fps(cls, output: str) -> float | None:
        match = cls._FPS_RE.search(output)
        if not match:
            return None
        try:
            value = float(match.group(1))
        except ValueError:
            return None
        return value if 1 <= value <= 240 else None
