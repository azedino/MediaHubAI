from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from core.models import TranscriptSegment


class BaseTranscriber(ABC):
    @abstractmethod
    def transcribe(
        self,
        source: str | Path,
        model_name: str,
        language: str | None = None,
    ) -> list[TranscriptSegment]:
        raise NotImplementedError


class BaseLLM(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        raise NotImplementedError


class ProviderManager:
    def __init__(self, transcribers: dict[str, BaseTranscriber], llms: dict[str, BaseLLM]) -> None:
        self.transcribers = transcribers
        self.llms = llms

    def get_transcriber(self, provider_key: str) -> BaseTranscriber:
        if provider_key not in self.transcribers:
            raise KeyError(f"Transcriber provider not registered: {provider_key}")
        return self.transcribers[provider_key]

    def get_llm(self, provider_key: str) -> BaseLLM:
        if provider_key not in self.llms:
            raise KeyError(f"LLM provider not registered: {provider_key}")
        return self.llms[provider_key]
