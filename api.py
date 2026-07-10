from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

from core.catalogs import LLM_MODELS, SHORT_TEMPLATES, TRANSCRIPTION_MODELS
from downloaders import UniversalDownloader
from services import ShortCreationService
from services.hardware import HardwareSelector
from services.transcription import WhisperTranscriber

app = FastAPI(title="Media Hub AI Backend")

DOWNLOAD_DIR = Path(os.getenv("CLIPFORGE_DOWNLOAD_DIR", Path.cwd() / "downloads")).resolve()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


class DownloadRequest(BaseModel):
    url: str
    platform: str | None = None
    selected_format: str = Field("Video")
    quality: str = Field("Best")
    file_ext: str = Field("mp4")
    filename: str | None = None

    @validator("url")
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL deve iniciar com http:// ou https://")
        return value


class ShortsRequestModel(BaseModel):
    source: str
    output_dir: str
    preset: str = "youtube_shorts"
    clips_count: int = 3
    target_duration: float = 30.0
    speed: float = 1.0
    mirror: bool = False
    filter_preset: str = "vibrant"
    template: str = "blur_background"
    captions_enabled: bool = True
    caption_preset: str = "viral"
    caption_font: str = "Arial"
    language: str | None = None
    whisper_model: str = "small"
    execution_device: str = "auto"

    @validator("clips_count")
    def validate_clips_count(cls, value: int) -> int:
        if not 1 <= value <= 10:
            raise ValueError("A quantidade de cortes deve estar entre 1 e 10.")
        return value

    @validator("target_duration")
    def validate_target_duration(cls, value: float) -> float:
        if not 5 <= value <= 180:
            raise ValueError("A duracao deve estar entre 5 e 180 segundos.")
        return value

    @validator("speed")
    def validate_speed(cls, value: float) -> float:
        if not 0.5 <= value <= 2.0:
            raise ValueError("A velocidade deve estar entre 0.5x e 2.0x.")
        return value


class DownloadResponse(BaseModel):
    output_path: str


class ShortsResponse(BaseModel):
    outputs: list[str]
    warnings: list[str] = []
    reaction: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/options")
def options() -> dict:
    device = HardwareSelector().resolve("auto")
    return {
        "transcription_models": [asdict(model) for model in TRANSCRIPTION_MODELS],
        "llm_models": [asdict(model) for model in LLM_MODELS],
        "templates": [asdict(template) for template in SHORT_TEMPLATES],
        "execution": {
            "choices": ["auto", "cpu", "gpu"],
            "detected": asdict(device),
        },
    }


@app.post("/download", response_model=DownloadResponse)
def download_media(request: DownloadRequest) -> DownloadResponse:
    downloader = UniversalDownloader()
    try:
        path = downloader.download(
            request.url,
            DOWNLOAD_DIR,
            selected_format=request.selected_format,
            quality=request.quality,
            file_ext=request.file_ext,
            filename=request.filename,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DownloadResponse(output_path=str(path))


@app.post("/shorts", response_model=ShortsResponse)
def generate_shorts(request: ShortsRequestModel) -> ShortsResponse:
    from core.models import (
        CaptionPreset,
        ExportPreset,
        FilterPreset,
        ShortTemplate,
    )
    from core.models import (
        ShortsRequest as ShortsRequestModelCore,
    )

    output_dir = Path(request.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        source_path = Path(request.source).expanduser().resolve()
        if not source_path.is_file():
            raise ValueError("Arquivo de origem nao encontrado.")

        short_request = ShortsRequestModelCore(
            source=source_path,
            output_dir=output_dir,
            preset=ExportPreset(request.preset),
            clips_count=request.clips_count,
            target_duration=request.target_duration,
            speed=request.speed,
            mirror=request.mirror,
            filter_preset=FilterPreset(request.filter_preset),
            template=ShortTemplate(request.template),
            captions_enabled=request.captions_enabled,
            caption_preset=CaptionPreset(request.caption_preset),
            caption_font=request.caption_font,
            language=request.language,
            whisper_model=request.whisper_model,
            execution_device=request.execution_device,
        )
        service = ShortCreationService(transcriber=WhisperTranscriber())
        result = service.create(short_request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ShortsResponse(
        outputs=[str(output) for output in result.outputs],
        warnings=result.warnings,
        reaction=(result.reaction.reason if result.reaction.reason else None),
    )
