from __future__ import annotations

from pathlib import Path

from core.errors import DependencyUnavailableError
from core.models import TranscriptSegment, TranscriptWord
from providers.base import BaseTranscriber


class OpenAITranscriber(BaseTranscriber):
    def __init__(self, client_factory) -> None:
        self.client_factory = client_factory

    def transcribe(
        self,
        source: str | Path,
        model_name: str,
        language: str | None = None,
    ) -> list[TranscriptSegment]:
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise DependencyUnavailableError("openai package is required for OpenAI transcription") from exc

        path = Path(source).resolve()
        if not path.is_file():
            raise DependencyUnavailableError(f"Arquivo de origem não encontrado: {path}")

        client = self.client_factory()
        with path.open("rb") as audio_file:
            response = client.audio.transcriptions.create(
                file=audio_file,
                model=model_name,
                response_format="verbose_json",
                language=language or None,
            )

        segments = getattr(response, "segments", None) or response.get("segments", [])
        result: list[TranscriptSegment] = []
        for segment in segments:
            words = tuple(
                TranscriptWord(
                    text=(word.get("word") or "").strip(),
                    start=float(word.get("start", 0.0)),
                    end=float(word.get("end", 0.0)),
                    probability=float(word.get("confidence", 1.0) or 0.0),
                )
                for word in segment.get("words", [])
                if (word.get("word") or "").strip()
            )
            text = (segment.get("text") or "").strip()
            if text:
                result.append(
                    TranscriptSegment(
                        text=text,
                        start=float(segment.get("start", 0.0)),
                        end=float(segment.get("end", 0.0)),
                        words=words,
                    )
                )
        return result
