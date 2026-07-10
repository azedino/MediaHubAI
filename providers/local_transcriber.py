from __future__ import annotations

from pathlib import Path
from typing import Any

from core.errors import DependencyUnavailableError
from core.models import TranscriptSegment, TranscriptWord
from providers.base import BaseTranscriber


class LocalWhisperTranscriber(BaseTranscriber):
    def __init__(self, default_device: str = "cpu", default_compute_type: str | None = None) -> None:
        self.default_device = default_device
        self.default_compute_type = default_compute_type
        self._models: dict[tuple[str, str, str], Any] = {}

    def transcribe(
        self,
        source: str | Path,
        model_name: str,
        language: str | None = None,
    ) -> list[TranscriptSegment]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise DependencyUnavailableError("faster-whisper is required for local transcription") from exc

        path = Path(source).resolve()
        if not path.is_file():
            raise DependencyUnavailableError(f"Arquivo de origem não encontrado: {path}")

        device = self.default_device.lower()
        compute_type = self.default_compute_type or ("float16" if device == "cuda" else "int8")
        cache_key = (model_name, device, compute_type)
        model = self._models.get(cache_key)
        if model is None:
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            self._models[cache_key] = model

        raw_segments, _ = model.transcribe(
            str(path),
            language=language or None,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 350},
            condition_on_previous_text=False,
        )

        result: list[TranscriptSegment] = []
        for segment in raw_segments:
            words = tuple(
                TranscriptWord(
                    text=(word.word or "").strip(),
                    start=float(word.start),
                    end=float(word.end),
                    probability=float(getattr(word, "probability", 1.0) or 0.0),
                )
                for word in (segment.words or [])
                if (word.word or "").strip()
            )
            text = (segment.text or "").strip()
            if text:
                result.append(
                    TranscriptSegment(
                        text=text,
                        start=float(segment.start),
                        end=float(segment.end),
                        words=words,
                    )
                )
        return result
