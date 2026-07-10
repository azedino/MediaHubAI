"""Detect stable picture-in-picture webcam regions before rendering."""

from __future__ import annotations

import statistics
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.models import MediaInfo

from .geometry import BoundingBox
from .shorts_config import DetectionConfig
from .tracker import OpenCVBoxTracker, TemporalBoxSmoother


@dataclass(frozen=True, slots=True)
class WebcamDetection:
    detected: bool
    confidence: float
    webcam_box: BoundingBox | None
    face_box: BoundingBox | None
    reason: str
    method: str = "none"
    samples: int = 0


@dataclass(frozen=True, slots=True)
class _FrameCandidate:
    webcam_box: BoundingBox
    face_box: BoundingBox | None
    score: float
    method: str


class WebcamDetector:
    """Multi-pass detector: rectangular PiP panels, face-seeded panels, then tracking."""

    def __init__(self, config: DetectionConfig | None = None) -> None:
        self._config = config or DetectionConfig()

    def detect(
        self,
        source: str | Path,
        media: MediaInfo,
        *,
        cancel_event: threading.Event | None = None,
    ) -> WebcamDetection:
        try:
            import cv2
        except ImportError:
            return WebcamDetection(
                detected=False,
                confidence=0.0,
                webcam_box=None,
                face_box=None,
                reason="OpenCV is not installed; webcam-aware layout is disabled.",
            )

        capture = cv2.VideoCapture(str(Path(source).resolve()))
        if not capture.isOpened():
            return WebcamDetection(False, 0.0, None, None, "Could not sample frames for webcam detection.")

        candidates: list[_FrameCandidate] = []
        sample_times = self._sample_times(media.duration)
        try:
            for timestamp in sample_times:
                if cancel_event and cancel_event.is_set():
                    break
                capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                ok, frame = capture.read()
                if not ok:
                    continue
                frame_candidates = self._detect_frame_candidates(cv2, frame, media)
                if frame_candidates:
                    candidates.append(max(frame_candidates, key=lambda item: item.score))
        finally:
            capture.release()

        if len(candidates) < self._config.min_sample_hits:
            return WebcamDetection(
                False,
                0.0,
                None,
                None,
                "No persistent webcam panel was found in sampled frames.",
                samples=len(candidates),
            )

        clustered = self._stable_cluster(candidates, media)
        if clustered is None:
            return WebcamDetection(
                False,
                0.0,
                None,
                None,
                "Webcam-like detections were too inconsistent to freeze safely.",
                samples=len(candidates),
            )

        tracked_box = self._track_sampled_frames(
            cv2,
            source,
            media,
            clustered.webcam_box,
            sample_times,
            cancel_event,
        )
        final_box = tracked_box or clustered.webcam_box
        confidence = self._confidence(candidates, clustered.webcam_box, len(sample_times))
        detected = confidence >= self._config.min_confidence
        reason = (
            "Stable webcam panel detected and frozen for FFmpeg rendering."
            if detected
            else "Webcam panel confidence was below the production threshold."
        )
        return WebcamDetection(
            detected=detected,
            confidence=round(confidence, 2),
            webcam_box=final_box if detected else None,
            face_box=clustered.face_box,
            reason=reason,
            method=clustered.method,
            samples=len(candidates),
        )

    def _detect_frame_candidates(self, cv2: Any, frame: Any, media: MediaInfo) -> list[_FrameCandidate]:
        candidates = self._detect_rectangular_panels(cv2, frame, media)
        candidates.extend(self._detect_face_seeded_panels(cv2, frame, media))
        return candidates

    def _detect_rectangular_panels(self, cv2: Any, frame: Any, media: MediaInfo) -> list[_FrameCandidate]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 70, 160)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = media.width * media.height
        candidates: list[_FrameCandidate] = []
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            box = BoundingBox(int(x), int(y), int(width), int(height)).clamp(media.width, media.height)
            area_ratio = box.area / max(1, frame_area)
            if not 0.025 <= area_ratio <= 0.36:
                continue
            if not 0.55 <= box.aspect_ratio <= 2.20:
                continue
            if not self._near_edge(box, media):
                continue
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
            rectangularity = min(1.0, len(approx) / 4.0) if len(approx) <= 6 else 0.45
            edge_score = self._edge_score(box, media)
            score = 0.50 + rectangularity * 0.22 + edge_score * 0.28
            candidates.append(_FrameCandidate(box, None, min(0.95, score), "panel-contour"))
        return candidates

    def _detect_face_seeded_panels(self, cv2: Any, frame: Any, media: MediaInfo) -> list[_FrameCandidate]:
        cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        cascade = cv2.CascadeClassifier(cascade_path)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.10, minNeighbors=5, minSize=(36, 36))
        candidates: list[_FrameCandidate] = []
        for x, y, width, height in faces:
            face = BoundingBox(int(x), int(y), int(width), int(height)).clamp(media.width, media.height)
            area_ratio = face.area / max(1, media.width * media.height)
            if area_ratio > 0.16:
                continue
            if not self._near_edge(face, media):
                continue
            panel = self._panel_from_face(face, media)
            edge_score = self._edge_score(panel, media)
            face_score = max(0.0, min(1.0, 0.16 - area_ratio) / 0.16)
            score = 0.56 + edge_score * 0.24 + face_score * 0.20
            candidates.append(_FrameCandidate(panel, face, min(0.98, score), "face-seeded-panel"))
        return candidates

    def _track_sampled_frames(
        self,
        cv2: Any,
        source: str | Path,
        media: MediaInfo,
        initial_box: BoundingBox,
        sample_times: list[float],
        cancel_event: threading.Event | None,
    ) -> BoundingBox | None:
        capture = cv2.VideoCapture(str(Path(source).resolve()))
        if not capture.isOpened() or not sample_times:
            return None
        tracker = OpenCVBoxTracker(cv2)
        smoother = TemporalBoxSmoother(initial_box, self._config)
        initialized = False
        try:
            for timestamp in sample_times:
                if cancel_event and cancel_event.is_set():
                    break
                capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                ok, frame = capture.read()
                if not ok:
                    continue
                if not initialized:
                    initialized = tracker.initialize(frame, initial_box)
                    continue
                update = tracker.update(frame)
                tracking_is_valid = (
                    update.ok
                    and update.box
                    and update.box.iou(smoother.current) >= self._config.tracker_min_iou
                )
                if tracking_is_valid:
                    smoother.update(update.box.clamp(media.width, media.height))
        finally:
            capture.release()
        return smoother.current if initialized else None

    def _stable_cluster(self, candidates: list[_FrameCandidate], media: MediaInfo) -> _FrameCandidate | None:
        best = max(candidates, key=lambda item: item.score)
        cluster = [item for item in candidates if item.webcam_box.iou(best.webcam_box) >= 0.28]
        if len(cluster) < self._config.min_sample_hits:
            return None
        xs = [item.webcam_box.x for item in cluster]
        ys = [item.webcam_box.y for item in cluster]
        widths = [item.webcam_box.width for item in cluster]
        heights = [item.webcam_box.height for item in cluster]
        webcam_box = BoundingBox(
            round(statistics.median(xs)),
            round(statistics.median(ys)),
            round(statistics.median(widths)),
            round(statistics.median(heights)),
        ).clamp(media.width, media.height)
        face_boxes = [item.face_box for item in cluster if item.face_box is not None]
        face_box = self._median_box(face_boxes, media) if face_boxes else None
        method = max(cluster, key=lambda item: item.score).method
        return _FrameCandidate(webcam_box, face_box, statistics.mean(item.score for item in cluster), method)

    def _confidence(self, candidates: list[_FrameCandidate], box: BoundingBox, sample_count: int) -> float:
        cluster_hits = sum(1 for item in candidates if item.webcam_box.iou(box) >= 0.28)
        persistence = cluster_hits / max(1, sample_count)
        quality = statistics.mean(item.score for item in candidates)
        return min(0.99, quality * 0.62 + persistence * 0.38)

    def _sample_times(self, duration: float) -> list[float]:
        if duration <= 0:
            return []
        count = max(4, min(24, self._config.samples))
        return [duration * (index + 1) / (count + 1) for index in range(count)]

    @staticmethod
    def _panel_from_face(face: BoundingBox, media: MediaInfo) -> BoundingBox:
        center_x, center_y = face.center
        target_ratio = 16 / 9
        panel_height = max(face.height * 3.4, media.height * 0.20)
        panel_width = panel_height * target_ratio
        if panel_width > media.width * 0.48:
            panel_width = media.width * 0.48
            panel_height = panel_width / target_ratio

        x = round(center_x - panel_width / 2)
        y = round(center_y - panel_height * 0.42)
        if center_x < media.width * 0.35:
            x = min(x, round(media.width * 0.03))
        elif center_x > media.width * 0.65:
            x = max(x, round(media.width - panel_width - media.width * 0.03))
        if center_y < media.height * 0.35:
            y = min(y, round(media.height * 0.03))
        elif center_y > media.height * 0.65:
            y = max(y, round(media.height - panel_height - media.height * 0.03))
        return BoundingBox(x, y, round(panel_width), round(panel_height)).clamp(media.width, media.height)

    @staticmethod
    def _median_box(boxes: list[BoundingBox], media: MediaInfo) -> BoundingBox:
        return BoundingBox(
            round(statistics.median(box.x for box in boxes)),
            round(statistics.median(box.y for box in boxes)),
            round(statistics.median(box.width for box in boxes)),
            round(statistics.median(box.height for box in boxes)),
        ).clamp(media.width, media.height)

    @staticmethod
    def _near_edge(box: BoundingBox, media: MediaInfo) -> bool:
        center_x, center_y = box.center
        nx = center_x / max(1, media.width)
        ny = center_y / max(1, media.height)
        return nx < 0.35 or nx > 0.65 or ny < 0.35 or ny > 0.65

    @staticmethod
    def _edge_score(box: BoundingBox, media: MediaInfo) -> float:
        left = box.x / max(1, media.width)
        right = (media.width - box.x - box.width) / max(1, media.width)
        top = box.y / max(1, media.height)
        bottom = (media.height - box.y - box.height) / max(1, media.height)
        nearest = min(left, right, top, bottom)
        return max(0.0, min(1.0, 1.0 - nearest / 0.22))
