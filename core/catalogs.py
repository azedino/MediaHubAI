from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelOption:
    id: str
    label: str
    provider: str
    group: str
    description: str
    capabilities: str
    speed: str
    vram: str
    ram: str
    location: str


@dataclass(frozen=True, slots=True)
class TemplateOption:
    id: str
    label: str
    description: str
    recommended_use: str
    aspect_ratio: str
    webcam_position: str
    subtitle_style: str
    preview: str


TRANSCRIPTION_MODELS: tuple[ModelOption, ...] = (
    ModelOption(
        "tiny",
        "Faster Whisper Tiny",
        "Faster Whisper",
        "Transcription",
        "Very fast draft captions.",
        "transcription, timestamps",
        "Very fast",
        "1 GB",
        "2 GB",
        "Local",
    ),
    ModelOption(
        "small",
        "Faster Whisper Small",
        "Faster Whisper",
        "Transcription",
        "Balanced local Portuguese and English transcription.",
        "transcription, timestamps",
        "Fast",
        "2 GB",
        "4 GB",
        "Local",
    ),
    ModelOption(
        "medium",
        "Faster Whisper Medium",
        "Faster Whisper",
        "Transcription",
        "Better accuracy for noisy social clips.",
        "transcription, timestamps",
        "Medium",
        "5 GB",
        "8 GB",
        "Local",
    ),
    ModelOption(
        "large-v3",
        "Faster Whisper Large v3",
        "Faster Whisper",
        "Transcription",
        "Highest local accuracy when hardware allows it.",
        "transcription, timestamps",
        "Slow",
        "10 GB",
        "16 GB",
        "Local",
    ),
    ModelOption(
        "whisper-1",
        "OpenAI Whisper",
        "OpenAI",
        "Transcription",
        "Cloud transcription with no local GPU requirement.",
        "transcription",
        "Fast",
        "0 GB",
        "1 GB",
        "Cloud",
    ),
    ModelOption(
        "whisper-large-v3",
        "Groq Whisper",
        "Groq",
        "Transcription",
        "Fast cloud Whisper-compatible transcription.",
        "transcription",
        "Very fast",
        "0 GB",
        "1 GB",
        "Cloud",
    ),
    ModelOption(
        "assemblyai",
        "AssemblyAI",
        "AssemblyAI",
        "Transcription",
        "Cloud transcription with diarization-friendly roadmap.",
        "transcription, diarization",
        "Fast",
        "0 GB",
        "1 GB",
        "Cloud",
    ),
)

LLM_MODELS: tuple[ModelOption, ...] = (
    ModelOption(
        "gpt-4.1",
        "GPT-4.1",
        "OpenAI",
        "LLM",
        "High quality reasoning for hooks and clip scoring.",
        "analysis, copywriting",
        "Fast",
        "0 GB",
        "1 GB",
        "Cloud",
    ),
    ModelOption(
        "claude",
        "Claude",
        "Anthropic",
        "LLM",
        "Strong editorial analysis and summarization.",
        "analysis, copywriting",
        "Fast",
        "0 GB",
        "1 GB",
        "Cloud",
    ),
    ModelOption(
        "gemini",
        "Gemini",
        "Google",
        "LLM",
        "Multimodal-friendly cloud model family.",
        "analysis, multimodal",
        "Fast",
        "0 GB",
        "1 GB",
        "Cloud",
    ),
    ModelOption(
        "groq",
        "Groq",
        "LLM",
        "LLM",
        "Low-latency text generation for iteration.",
        "analysis, copywriting",
        "Very fast",
        "0 GB",
        "1 GB",
        "Cloud",
    ),
    ModelOption(
        "openrouter",
        "OpenRouter",
        "OpenRouter",
        "LLM",
        "Provider router for future model selection.",
        "analysis, routing",
        "Variable",
        "0 GB",
        "1 GB",
        "Cloud",
    ),
)

SHORT_TEMPLATES: tuple[TemplateOption, ...] = (
    TemplateOption(
        "fill",
        "Vertical Focus",
        "Full-screen crop for already vertical or centered content.",
        "Talking-head shorts",
        "9:16",
        "None",
        "Viral",
        "assets/templates/vertical_focus.png",
    ),
    TemplateOption(
        "blur_background",
        "Horizontal Focus",
        "Keeps horizontal video visible over a soft background.",
        "Podcasts, webinars, YouTube clips",
        "9:16",
        "None",
        "Clean",
        "assets/templates/horizontal_focus.png",
    ),
    TemplateOption(
        "reaction_top",
        "Reaction Top",
        "Places detected webcam in the upper corner.",
        "Reaction content",
        "9:16",
        "Top right",
        "Viral",
        "assets/templates/reaction_top.png",
    ),
    TemplateOption(
        "reaction_bottom",
        "Reaction Bottom",
        "Places detected webcam near the lower corner.",
        "Commentary and reactions",
        "9:16",
        "Bottom right",
        "Viral",
        "assets/templates/reaction_bottom.png",
    ),
    TemplateOption(
        "split",
        "Split Screen",
        "Separates main content and webcam into a structured split.",
        "Interviews and debates",
        "9:16",
        "Right side",
        "Clean",
        "assets/templates/split_screen.png",
    ),
    TemplateOption(
        "gameplay",
        "Gameplay",
        "Prioritizes action framing and caption-safe lower thirds.",
        "Gaming and livestream clips",
        "9:16",
        "Optional",
        "Neon",
        "assets/templates/gameplay.png",
    ),
    TemplateOption(
        "podcast",
        "Podcast",
        "Stable crop with readable captions for long-form discussions.",
        "Podcasts",
        "9:16",
        "None",
        "Clean",
        "assets/templates/podcast.png",
    ),
    TemplateOption(
        "interview",
        "Interview",
        "Balanced framing for two-person clips.",
        "Interviews",
        "9:16",
        "Optional",
        "Clean",
        "assets/templates/interview.png",
    ),
    TemplateOption(
        "educational",
        "Educational",
        "Readable composition for explainers and tutorials.",
        "Courses and explainers",
        "9:16",
        "None",
        "Minimal",
        "assets/templates/educational.png",
    ),
    TemplateOption(
        "news",
        "News",
        "High-contrast editorial layout for updates.",
        "News and commentary",
        "9:16",
        "None",
        "Clean",
        "assets/templates/news.png",
    ),
    TemplateOption(
        "commentary",
        "Commentary",
        "Designed for opinion clips with optional reaction framing.",
        "Commentary videos",
        "9:16",
        "Optional",
        "Viral",
        "assets/templates/commentary.png",
    ),
    TemplateOption(
        "dynamic_zoom",
        "Dynamic Zoom",
        "Crops tighter for stronger mobile emphasis.",
        "Highlights and punchlines",
        "9:16",
        "None",
        "Viral",
        "assets/templates/dynamic_zoom.png",
    ),
)


def model_choices(group: str) -> tuple[ModelOption, ...]:
    if group == "LLM":
        return LLM_MODELS
    return TRANSCRIPTION_MODELS


def template_by_id(template_id: str) -> TemplateOption:
    for template in SHORT_TEMPLATES:
        if template.id == template_id:
            return template
    return SHORT_TEMPLATES[0]
