"""Audio transcription with cloud support and local faster-whisper fallback."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from core.errors import DependencyUnavailableError, JobCancelledError
from core.models import TranscriptSegment, TranscriptWord
from services.hardware import HardwareSelector

StatusCallback = Callable[[str], None]


class WhisperTranscriber:
    _models: dict[tuple[str, str, str], Any] = {}
    _model_lock = threading.Lock()

    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY")) or self._is_local_available()

    def transcribe(
        self,
        source: str | Path,
        *,
        model_name: str = "whisper-1",
        language: str | None = None,
        execution_device: str = "auto",
        status_callback: StatusCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[TranscriptSegment]:
        if status_callback:
            status_callback("Iniciando transcricao de audio...")

        if self._should_use_openai(model_name):
            return self._transcribe_api(source, model_name, language, status_callback, cancel_event)
        return self._transcribe_local(
            source,
            model_name,
            language,
            execution_device,
            status_callback,
            cancel_event,
        )

    def _transcribe_api(
        self,
        source: str | Path,
        model_name: str,
        language: str | None,
        status_callback: StatusCallback | None,
        cancel_event: threading.Event | None,
    ) -> list[TranscriptSegment]:
        if not self._has_openai_key():
            raise DependencyUnavailableError(
                f"O modelo '{model_name}' exige uma chave de API configurada no ambiente."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise DependencyUnavailableError("A transcricao em nuvem requer o pacote openai.") from exc

        if cancel_event and cancel_event.is_set():
            raise JobCancelledError("Criacao cancelada.")
        if status_callback:
            status_callback("Transcrevendo com OpenAI...")

        client = OpenAI()
        path = Path(source).resolve()
        if not path.is_file():
            raise DependencyUnavailableError(f"Arquivo de audio nao encontrado: {path}")

        try:
            with path.open("rb") as audio_file:
                request_args: dict[str, Any] = {
                    "file": audio_file,
                    "model": model_name,
                    "response_format": "verbose_json",
                }
                if language is not None:
                    request_args["language"] = language
                response = client.audio.transcriptions.create(**request_args)
        except Exception as exc:
            raise DependencyUnavailableError(f"Falha na transcricao em nuvem: {exc}") from exc

        text = getattr(response, "text", None) or response.get("text", "")
        segments = getattr(response, "segments", None) or response.get("segments", None) or []
        if not segments:
            return [TranscriptSegment(text=text.strip(), start=0.0, end=0.0, words=())] if text else []

        result: list[TranscriptSegment] = []
        for segment in segments:
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError("Criacao cancelada.")
            segment_text = (segment.get("text") or "").strip()
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", 0.0))
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
            if segment_text:
                result.append(TranscriptSegment(text=segment_text, start=start, end=end, words=words))
        return result

    def _transcribe_local(
        self,
        source: str | Path,
        model_name: str,
        language: str | None,
        execution_device: str,
        status_callback: StatusCallback | None,
        cancel_event: threading.Event | None,
    ) -> list[TranscriptSegment]:
        if find_spec("faster_whisper") is None:
            raise DependencyUnavailableError(
                "Legendas automaticas exigem faster-whisper ou um modelo de nuvem configurado."
            )

        selected_device = HardwareSelector().resolve(
            execution_device or os.environ.get("CLIPFORGE_WHISPER_DEVICE", "auto")
        )
        device = selected_device.device if selected_device.device in {"cpu", "cuda"} else "cpu"
        if status_callback:
            if device == "cuda":
                suffix = f" usando {selected_device.label}"
                if selected_device.gpu_name:
                    suffix += f" ({selected_device.gpu_name})"
            else:
                suffix = " usando CPU"
            status_callback(f"Carregando IA local ({model_name}){suffix}.")
            if selected_device.fallback_reason:
                status_callback(selected_device.fallback_reason)
            if selected_device.device not in {"cpu", "cuda"}:
                status_callback(
                    "GPU AMD/Intel detectada para renderizacao; transcricao local continua em CPU."
                )

        default_compute_type = "float16" if device == "cuda" else "int8"
        compute_type = os.environ.get("CLIPFORGE_WHISPER_COMPUTE_TYPE", default_compute_type).strip()
        model = self._load_local_model(model_name, device, compute_type, status_callback)

        if cancel_event and cancel_event.is_set():
            raise JobCancelledError("Criacao cancelada.")
        if status_callback:
            status_callback("Transcrevendo e detectando pausas localmente...")

        try:
            raw_segments, _ = model.transcribe(
                str(Path(source).resolve()),
                language=language or None,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 350},
                condition_on_previous_text=False,
            )
            result: list[TranscriptSegment] = []
            for segment in raw_segments:
                if cancel_event and cancel_event.is_set():
                    raise JobCancelledError("Criacao cancelada.")
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
        except JobCancelledError:
            raise
        except Exception as exc:
            raise DependencyUnavailableError(f"Falha na transcricao local: {exc}") from exc

    def _load_local_model(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        status_callback: StatusCallback | None,
    ) -> Any:
        from faster_whisper import WhisperModel

        cache_key = (model_name, device, compute_type)
        with self._model_lock:
            model = self._models.get(cache_key)
            if model is not None:
                return model
            try:
                model = WhisperModel(model_name, device=device, compute_type=compute_type)
            except Exception as exc:
                if device != "cuda":
                    raise DependencyUnavailableError(
                        f"Nao foi possivel carregar o modelo local '{model_name}': {exc}"
                    ) from exc
                if status_callback:
                    status_callback("GPU indisponivel para este modelo; continuando em CPU.")
                cache_key = (model_name, "cpu", "int8")
                model = self._models.get(cache_key)
                if model is None:
                    model = WhisperModel(model_name, device="cpu", compute_type="int8")
            self._models[cache_key] = model
            return model

    @staticmethod
    def _should_use_openai(model_name: str) -> bool:
        return model_name == "whisper-1"

    @staticmethod
    def _has_openai_key() -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    @staticmethod
    def _is_local_available() -> bool:
        return find_spec("faster_whisper") is not None
