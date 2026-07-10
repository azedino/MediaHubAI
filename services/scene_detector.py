"""Scene detection adapter kept separate from rendering orchestration."""

from __future__ import annotations

import threading
from pathlib import Path

from .ffmpeg import FFmpegService


class SceneDetector:
    def __init__(self, ffmpeg: FFmpegService) -> None:
        self._ffmpeg = ffmpeg

    def detect(self, source: str | Path, *, cancel_event: threading.Event | None = None) -> list[float]:
        return self._ffmpeg.detect_scene_changes(source, cancel_event=cancel_event)
