"""Video metadata loading entry point for the shorts pipeline."""

from __future__ import annotations

from pathlib import Path

from core.models import MediaInfo

from .ffmpeg import FFmpegService


class VideoLoader:
    def __init__(self, ffmpeg: FFmpegService) -> None:
        self._ffmpeg = ffmpeg

    def load(self, source: str | Path) -> MediaInfo:
        return self._ffmpeg.probe(source)
