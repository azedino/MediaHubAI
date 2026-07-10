"""Modelos imutáveis compartilhados pelo download e pelo estúdio de shorts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .errors import InvalidMediaError


class StringEnum(StrEnum):
    pass


class MediaType(StringEnum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"


class ExportPreset(StringEnum):
    YOUTUBE_SHORTS = "youtube_shorts"
    TIKTOK = "tiktok"
    INSTAGRAM_REELS = "instagram_reels"
    VERTICAL_FEED = "vertical_feed"
    SQUARE = "square"

    @property
    def dimensions(self) -> tuple[int, int]:
        return {
            self.YOUTUBE_SHORTS: (1080, 1920),
            self.TIKTOK: (1080, 1920),
            self.INSTAGRAM_REELS: (1080, 1920),
            self.VERTICAL_FEED: (1080, 1350),
            self.SQUARE: (1080, 1080),
        }[self]

    @property
    def display_name(self) -> str:
        return {
            self.YOUTUBE_SHORTS: "YouTube Shorts • 9:16",
            self.TIKTOK: "TikTok • 9:16",
            self.INSTAGRAM_REELS: "Instagram Reels • 9:16",
            self.VERTICAL_FEED: "Feed vertical • 4:5",
            self.SQUARE: "Quadrado • 1:1",
        }[self]


class CaptionPreset(StringEnum):
    VIRAL = "viral"
    CLEAN = "clean"
    NEON = "neon"
    MINIMAL = "minimal"


class ShortTemplate(StringEnum):
    AUTO = "auto"
    FILL = "fill"
    BLUR_BACKGROUND = "blur_background"
    REACTION_TOP = "reaction_top"
    REACTION_BOTTOM = "reaction_bottom"
    SPLIT = "split"
    GAMEPLAY = "gameplay"
    PODCAST = "podcast"
    INTERVIEW = "interview"
    EDUCATIONAL = "educational"
    NEWS = "news"
    COMMENTARY = "commentary"
    DYNAMIC_ZOOM = "dynamic_zoom"


class FilterPreset(StringEnum):
    NONE = "none"
    VIBRANT = "vibrant"
    CINEMATIC = "cinematic"
    WARM = "warm"
    COOL = "cool"
    BLACK_AND_WHITE = "black_and_white"


@dataclass(frozen=True, slots=True)
class MediaInfo:
    path: Path
    duration: float
    width: int
    height: int
    has_audio: bool = True
    fps: float | None = None

    @property
    def is_vertical(self) -> bool:
        return self.height > self.width


@dataclass(frozen=True, slots=True)
class TranscriptWord:
    text: str
    start: float
    end: float
    probability: float = 1.0


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    text: str
    start: float
    end: float
    words: tuple[TranscriptWord, ...] = ()


@dataclass(frozen=True, slots=True)
class ClipCandidate:
    start: float
    end: float
    score: float
    title: str
    reasons: tuple[str, ...] = ()

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class ReactionAnalysis:
    detected: bool = False
    confidence: float = 0.0
    face_box: tuple[int, int, int, int] | None = None
    reason: str = ""
    webcam_box: tuple[int, int, int, int] | None = None
    method: str = "none"


@dataclass(slots=True)
class ShortsRequest:
    source: Path
    output_dir: Path
    preset: ExportPreset = ExportPreset.YOUTUBE_SHORTS
    clips_count: int = 3
    target_duration: float = 30.0
    speed: float = 1.0
    mirror: bool = False
    filter_preset: FilterPreset = FilterPreset.VIBRANT
    template: ShortTemplate = ShortTemplate.AUTO
    captions_enabled: bool = True
    caption_preset: CaptionPreset = CaptionPreset.VIRAL
    caption_font: str = "Arial"
    language: str | None = None
    whisper_model: str = "small"
    execution_device: str = "auto"
    auto_cut: bool = True

    def validate(self) -> None:
        if not self.source.is_file():
            raise InvalidMediaError(f"Arquivo de origem não encontrado: {self.source}")
        if not 1 <= self.clips_count <= 10:
            raise InvalidMediaError("A quantidade de cortes deve estar entre 1 e 10.")
        if not 5 <= self.target_duration <= 180:
            raise InvalidMediaError("A duração deve estar entre 5 e 180 segundos.")
        if not 0.5 <= self.speed <= 2.0:
            raise InvalidMediaError("A velocidade deve estar entre 0,5x e 2,0x.")
        self.output_dir.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class ShortsResult:
    outputs: list[Path] = field(default_factory=list)
    candidates: list[ClipCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reaction: ReactionAnalysis = field(default_factory=ReactionAnalysis)
