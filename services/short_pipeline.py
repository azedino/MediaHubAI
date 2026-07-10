"""Production-oriented orchestration for viral short generation."""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from core.errors import JobCancelledError
from core.models import (
    ClipCandidate,
    FilterPreset,
    MediaInfo,
    ReactionAnalysis,
    ShortsRequest,
    ShortsResult,
    ShortTemplate,
    TranscriptSegment,
)

from .captions import CaptionRenderer
from .ffmpeg import FFmpegService
from .reaction_detector import ReactionDetector
from .renderer import ShortRenderer
from .scene_detector import SceneDetector
from .shorts_config import RenderConfig
from .transcription import WhisperTranscriber
from .video_loader import VideoLoader
from .viral_analyzer import ViralClipAnalyzer

ProgressCallback = Callable[[float, str], None]

LOGGER = logging.getLogger(__name__)


class ShortPipeline:
    def __init__(
        self,
        *,
        ffmpeg: FFmpegService | None = None,
        transcriber: WhisperTranscriber | None = None,
        analyzer: ViralClipAnalyzer | None = None,
        reaction_detector: ReactionDetector | None = None,
        captions: CaptionRenderer | None = None,
        renderer: ShortRenderer | None = None,
        render_config: RenderConfig | None = None,
    ) -> None:
        self.render_config = render_config or RenderConfig()
        self.ffmpeg = ffmpeg or FFmpegService()
        self.video_loader = VideoLoader(self.ffmpeg)
        self.scene_detector = SceneDetector(self.ffmpeg)
        self.transcriber = transcriber or WhisperTranscriber()
        self.analyzer = analyzer or ViralClipAnalyzer()
        self.reaction_detector = reaction_detector or ReactionDetector()
        self.captions = captions or CaptionRenderer()
        self.renderer = renderer or ShortRenderer(self.ffmpeg, render_config=self.render_config)

    def create(
        self,
        request: ShortsRequest,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ShortsResult:
        request.validate()
        cancel_event = cancel_event or threading.Event()
        result = ShortsResult()

        self._emit(progress_callback, 0.01, "Reading video metadata...")
        media = self.video_loader.load(request.source)
        if media.duration < 1:
            raise ValueError("The video is too short for processing.")
        if request.preset.dimensions != (self.render_config.width, self.render_config.height):
            result.warnings.append("Production shorts are rendered as 1080x1920 regardless of UI preset.")
        self._check_cancel(cancel_event)

        transcript = self._transcribe_if_needed(request, media, result, progress_callback, cancel_event)

        self._check_cancel(cancel_event)
        self._emit(progress_callback, 0.30, "Detecting scene rhythm...")
        try:
            scene_changes = self.scene_detector.detect(media.path, cancel_event=cancel_event)
        except JobCancelledError:
            raise
        except Exception as exc:
            LOGGER.exception("Scene detection failed")
            scene_changes = []
            result.warnings.append(f"Simplified scene analysis: {exc}")

        self._check_cancel(cancel_event)
        self._emit(progress_callback, 0.40, "Detecting stable webcam panel...")
        try:
            result.reaction = self.reaction_detector.analyze(media.path, media, cancel_event=cancel_event)
        except Exception as exc:
            LOGGER.exception("Webcam detection failed")
            result.reaction = ReactionAnalysis(reason=f"Webcam detection skipped: {exc}")
            result.warnings.append(result.reaction.reason)

        source_window = min(media.duration, request.target_duration * request.speed)
        result.candidates = self.analyzer.analyze(
            transcript if request.auto_cut else [],
            media_duration=media.duration,
            target_duration=source_window,
            count=request.clips_count,
            scene_changes=scene_changes,
        )
        if not result.candidates:
            raise ValueError("Could not find a usable interval in the video.")

        self._emit(progress_callback, 0.46, "Cuts selected. Starting FFmpeg render...")
        with TemporaryDirectory(prefix="clipforge-", dir=request.output_dir) as temp_dir:
            for index, candidate in enumerate(result.candidates, start=1):
                self._check_cancel(cancel_event)
                base_progress = 0.46 + (index - 1) / len(result.candidates) * 0.54
                item_span = 0.54 / len(result.candidates)
                self._emit(
                    progress_callback,
                    base_progress,
                    f"Rendering short {index}/{len(result.candidates)} - score {candidate.score:.0f}",
                )
                output = self._render_candidate(
                    request=request,
                    media=media,
                    candidate=candidate,
                    transcript=transcript,
                    reaction=result.reaction,
                    index=index,
                    temp_dir=Path(temp_dir),
                    cancel_event=cancel_event,
                    progress_callback=lambda value, status, base=base_progress, span=item_span: self._emit(
                        progress_callback, base + value * span, status
                    ),
                )
                result.outputs.append(output)

        self._emit(progress_callback, 1.0, f"{len(result.outputs)} short(s) created.")
        return result

    def build_filter_graph(
        self,
        *,
        media: MediaInfo,
        width: int,
        height: int,
        speed: float,
        mirror: bool,
        filter_preset: FilterPreset,
        template: ShortTemplate,
        reaction: ReactionAnalysis,
        subtitle_path: Path | None,
    ) -> str:
        renderer = getattr(self, "renderer", None)
        if renderer is None:
            renderer = ShortRenderer(FFmpegService(), render_config=RenderConfig(width=width, height=height))
        return renderer.build_filter_graph(
            media=media,
            width=width,
            height=height,
            speed=speed,
            mirror=mirror,
            filter_preset=filter_preset,
            template=template,
            reaction=reaction,
            subtitle_path=subtitle_path,
        )

    def cancel(self) -> None:
        self.ffmpeg.cancel()

    def _transcribe_if_needed(
        self,
        request: ShortsRequest,
        media: MediaInfo,
        result: ShortsResult,
        progress_callback: ProgressCallback | None,
        cancel_event: threading.Event,
    ) -> list[TranscriptSegment]:
        if not (request.auto_cut or request.captions_enabled):
            return []
        self._emit(progress_callback, 0.04, "Preparing speech analysis...")
        try:
            return self.transcriber.transcribe(
                media.path,
                model_name=request.whisper_model,
                language=request.language,
                execution_device=request.execution_device,
                status_callback=lambda status: self._emit(progress_callback, 0.12, status),
                cancel_event=cancel_event,
            )
        except JobCancelledError:
            raise
        except Exception as exc:
            LOGGER.exception("Transcription failed")
            result.warnings.append(str(exc))
            if request.captions_enabled:
                result.warnings.append("The video was created without captions because transcription failed.")
            return []

    def _render_candidate(
        self,
        *,
        request: ShortsRequest,
        media: MediaInfo,
        candidate: ClipCandidate,
        transcript: list[TranscriptSegment],
        reaction: ReactionAnalysis,
        index: int,
        temp_dir: Path,
        cancel_event: threading.Event,
        progress_callback: ProgressCallback | None,
    ) -> Path:
        subtitle_path: Path | None = None
        if request.captions_enabled and transcript:
            subtitle_path = self.captions.write_ass(
                transcript,
                temp_dir / f"captions-{index:02d}.ass",
                clip_start=candidate.start,
                clip_end=candidate.end,
                width=self.render_config.width,
                height=self.render_config.height,
                preset=request.caption_preset,
                font_name=request.caption_font,
            )

        output = self._next_output_path(
            request.output_dir,
            request.source.stem,
            index,
            candidate.score,
        )
        self.renderer.render(
            media=media,
            start=candidate.start,
            duration=max(0.1, candidate.duration),
            output=output,
            speed=request.speed,
            mirror=request.mirror,
            filter_preset=request.filter_preset,
            template=self._resolve_template(request.template, media, reaction),
            reaction=reaction,
            subtitle_path=subtitle_path,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
            execution_device=request.execution_device,
        )
        return output

    @staticmethod
    def _resolve_template(
        requested: ShortTemplate,
        media: MediaInfo,
        reaction: ReactionAnalysis,
    ) -> ShortTemplate:
        if requested is not ShortTemplate.AUTO:
            return requested
        if reaction.detected:
            return ShortTemplate.REACTION_TOP
        return ShortTemplate.FILL if media.is_vertical else ShortTemplate.GAMEPLAY

    @staticmethod
    def _next_output_path(output_dir: Path, source_stem: str, index: int, score: float) -> Path:
        normalized = unicodedata.normalize("NFKD", source_stem)
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", ascii_name).strip("-_") or "video"
        base = f"{slug[:55]}_short_{index:02d}_score-{round(score):02d}"
        candidate = output_dir / f"{base}.mp4"
        suffix = 2
        while candidate.exists():
            candidate = output_dir / f"{base}_{suffix}.mp4"
            suffix += 1
        return candidate

    @staticmethod
    def _check_cancel(cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            raise JobCancelledError("Creation cancelled.")

    @staticmethod
    def _emit(callback: ProgressCallback | None, value: float, status: str) -> None:
        if callback:
            callback(max(0.0, min(1.0, value)), status)
