"""Compatibility adapter for reaction/webcam detection."""

from __future__ import annotations

import threading
from pathlib import Path

from core.models import MediaInfo, ReactionAnalysis

from .webcam_detector import WebcamDetector


class ReactionDetector:
    """Detects the webcam panel, not a raw face crop.

    The public name is kept because the Streamlit/API layer already exposes
    "reaction" metadata. Internally this delegates to WebcamDetector.
    """

    def __init__(self, webcam_detector: WebcamDetector | None = None) -> None:
        self._webcam_detector = webcam_detector or WebcamDetector()

    def analyze(
        self,
        source: str | Path,
        media: MediaInfo,
        *,
        samples: int = 10,
        cancel_event: threading.Event | None = None,
    ) -> ReactionAnalysis:
        del samples
        detection = self._webcam_detector.detect(source, media, cancel_event=cancel_event)
        return ReactionAnalysis(
            detected=detection.detected,
            confidence=detection.confidence,
            face_box=detection.face_box.as_tuple() if detection.face_box else None,
            reason=detection.reason,
            webcam_box=detection.webcam_box.as_tuple() if detection.webcam_box else None,
            method=detection.method,
        )
