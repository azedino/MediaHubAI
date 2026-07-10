"""Configuration objects for the production shorts pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RenderConfig:
    width: int = 1080
    height: int = 1920
    crf: int = 18
    software_preset: str = "veryfast"
    audio_bitrate: str = "192k"
    target_lufs: int = -14


@dataclass(frozen=True, slots=True)
class DetectionConfig:
    samples: int = 18
    min_confidence: float = 0.48
    min_sample_hits: int = 3
    tracker_min_iou: float = 0.15
    hysteresis_pixels: float = 14.0
    hysteresis_frames: int = 2
    ema_alpha: float = 0.18


@dataclass(frozen=True, slots=True)
class LayoutConfig:
    webcam_height_ratio: float = 0.30
    caption_height_ratio: float = 0.22
    gutter: int = 18
    background_blur: int = 28
    bottom_dim_alpha: float = 0.60
