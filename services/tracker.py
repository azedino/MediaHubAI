"""Temporal tracking and smoothing for stable webcam regions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .geometry import BoundingBox
from .shorts_config import DetectionConfig


class TemporalBoxSmoother:
    """EMA smoother with hysteresis to prevent tiny detection jitters."""

    def __init__(self, initial: BoundingBox, config: DetectionConfig) -> None:
        self._current = initial
        self._config = config
        self._pending = 0

    @property
    def current(self) -> BoundingBox:
        return self._current

    def update(self, candidate: BoundingBox) -> BoundingBox:
        displacement = self._current.distance_to(candidate)
        if displacement < self._config.hysteresis_pixels:
            self._pending = 0
            return self._current

        self._pending += 1
        if self._pending < self._config.hysteresis_frames:
            return self._current

        alpha = self._config.ema_alpha
        smoothed = BoundingBox(
            round(self._current.x * (1 - alpha) + candidate.x * alpha),
            round(self._current.y * (1 - alpha) + candidate.y * alpha),
            round(self._current.width * (1 - alpha) + candidate.width * alpha),
            round(self._current.height * (1 - alpha) + candidate.height * alpha),
        )
        self._current = smoothed.even()
        return self._current


@dataclass(frozen=True, slots=True)
class TrackerUpdate:
    ok: bool
    box: BoundingBox | None
    confidence: float


class OpenCVBoxTracker:
    """Thin wrapper around OpenCV trackers with graceful fallback."""

    def __init__(self, cv2_module: Any) -> None:
        self._cv2 = cv2_module
        self._tracker: Any | None = None

    def initialize(self, frame: Any, box: BoundingBox) -> bool:
        tracker = self._create_tracker()
        if tracker is None:
            return False
        self._tracker = tracker
        init_result = tracker.init(frame, tuple(int(value) for value in box.as_tuple()))
        return init_result is not False

    def update(self, frame: Any) -> TrackerUpdate:
        if self._tracker is None:
            return TrackerUpdate(False, None, 0.0)
        ok, raw_box = self._tracker.update(frame)
        if not ok:
            return TrackerUpdate(False, None, 0.0)
        x, y, width, height = (round(float(value)) for value in raw_box)
        return TrackerUpdate(True, BoundingBox(x, y, width, height).even(), 0.70)

    def _create_tracker(self) -> Any | None:
        factories = (
            ("legacy", "TrackerCSRT_create"),
            ("", "TrackerCSRT_create"),
            ("legacy", "TrackerKCF_create"),
            ("", "TrackerKCF_create"),
            ("legacy", "TrackerMIL_create"),
            ("", "TrackerMIL_create"),
        )
        for namespace, name in factories:
            owner = getattr(self._cv2, namespace, self._cv2) if namespace else self._cv2
            factory = getattr(owner, name, None)
            if factory is not None:
                return factory()
        return None
