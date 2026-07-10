"""Geração de legendas ASS estilizadas e sincronizadas por palavra."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from core.models import CaptionPreset, TranscriptSegment, TranscriptWord


@dataclass(frozen=True, slots=True)
class _Style:
    font_size: int
    primary: str
    secondary: str
    outline: str
    background: str
    bold: int
    border_style: int
    outline_size: int
    shadow: int
    margin_v_ratio: float


STYLES: dict[CaptionPreset, _Style] = {
    CaptionPreset.VIRAL: _Style(
        78, "&H00FFFFFF", "&H0000E8FF", "&H00101010", "&H70000000", -1, 1, 6, 2, 0.045
    ),
    CaptionPreset.CLEAN: _Style(
        64, "&H00FFFFFF", "&H00FFFFFF", "&H00202020", "&H60000000", -1, 1, 3, 1, 0.032
    ),
    CaptionPreset.NEON: _Style(72, "&H00FFF7FF", "&H00FF55E8", "&H00A31489", "&H50000000", -1, 1, 5, 2, 0.04),
    CaptionPreset.MINIMAL: _Style(
        56, "&H00FFFFFF", "&H00FFFFFF", "&H00303030", "&H78000000", 0, 3, 1, 0, 0.025
    ),
}


class CaptionRenderer:
    def write_ass(
        self,
        segments: list[TranscriptSegment],
        output: str | Path,
        *,
        clip_start: float,
        clip_end: float,
        width: int,
        height: int,
        preset: CaptionPreset,
        font_name: str,
    ) -> Path:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        style = STYLES[preset]
        scaled_font = max(36, round(style.font_size * height / 1920))
        margin_v = round(height * style.margin_v_ratio)
        safe_font = self._escape_field(font_name.strip() or "Arial")

        style_format = (
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
            "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,"
            "BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding"
        )
        style_line = (
            f"Style: Caption,{safe_font},{scaled_font},{style.primary},{style.secondary},"
            f"{style.outline},{style.background},{style.bold},0,0,0,100,100,0,0,"
            f"{style.border_style},{style.outline_size},{style.shadow},2,60,60,{margin_v},1"
        )
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
{style_format}
{style_line}

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
        events: list[str] = []
        for segment in segments:
            if segment.end <= clip_start or segment.start >= clip_end:
                continue
            words = self._segment_words(segment)
            for group in self._group_words(words):
                start = max(group[0].start, clip_start) - clip_start
                end = min(group[-1].end, clip_end) - clip_start
                if end - start < 0.08:
                    continue
                text = self._format_group(group, preset, width, height)
                events.append(
                    f"Dialogue: 0,{self._ass_time(start)},{self._ass_time(end)},Caption,,0,0,0,,{text}"
                )

        destination.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
        return destination

    @staticmethod
    def _segment_words(segment: TranscriptSegment) -> tuple[TranscriptWord, ...]:
        if segment.words:
            return segment.words
        tokens = segment.text.split()
        if not tokens:
            return ()
        duration = max(0.1, segment.end - segment.start)
        step = duration / len(tokens)
        return tuple(
            TranscriptWord(token, segment.start + i * step, segment.start + (i + 1) * step)
            for i, token in enumerate(tokens)
        )

    @staticmethod
    def _group_words(words: tuple[TranscriptWord, ...]) -> list[tuple[TranscriptWord, ...]]:
        groups: list[tuple[TranscriptWord, ...]] = []
        current: list[TranscriptWord] = []
        length = 0
        for word in words:
            clean = word.text.strip()
            if current and (len(current) >= 4 or length + len(clean) > 24):
                groups.append(tuple(current))
                current, length = [], 0
            current.append(word)
            length += len(clean) + 1
        if current:
            groups.append(tuple(current))
        return groups

    def _format_group(
        self,
        words: tuple[TranscriptWord, ...],
        preset: CaptionPreset,
        width: int,
        height: int,
    ) -> str:
        pieces: list[str] = []
        visible_words: list[str] = []
        for word in words:
            duration_cs = max(1, round((word.end - word.start) * 100))
            clean = self._escape_text(word.text)
            visible = clean.upper() if preset in {CaptionPreset.VIRAL, CaptionPreset.NEON} else clean
            visible_words.append(visible)
            if preset in {CaptionPreset.VIRAL, CaptionPreset.NEON}:
                clean = clean.upper()
                pieces.append(f"{{\\kf{duration_cs}}}{clean}")
            else:
                pieces.append(clean)
        text = self._wrap_caption(pieces, visible_words)
        x = width // 2
        y = height - round(height * 0.11)
        prefix = (
            f"{{\\an2\\pos({x},{y})\\fad(60,60)\\fscx96\\fscy96"
            "\\t(0,130,\\fscx106\\fscy106)\\t(130,250,\\fscx100\\fscy100)\\q2}"
        )
        return prefix + text

    @staticmethod
    def _wrap_caption(pieces: list[str], visible_words: list[str]) -> str:
        if len(pieces) <= 2:
            return " ".join(pieces)
        max_chars = 18
        lines: list[list[str]] = [[]]
        current_length = 0
        for piece, visible in zip(pieces, visible_words, strict=True):
            visible_length = len(visible)
            if lines[-1] and current_length + visible_length + 1 > max_chars and len(lines) < 2:
                lines.append([])
                current_length = 0
            lines[-1].append(piece)
            current_length += visible_length + 1
        return "\\N".join(" ".join(line) for line in lines if line)

    @staticmethod
    def _ass_time(seconds: float) -> str:
        seconds = max(0.0, seconds)
        hours = int(seconds // 3600)
        minutes = int(seconds % 3600 // 60)
        whole_seconds = int(seconds % 60)
        centiseconds = min(99, int(math.floor((seconds - int(seconds)) * 100)))
        return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"

    @staticmethod
    def _escape_text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")

    @staticmethod
    def _escape_field(value: str) -> str:
        return value.replace(",", " ").replace("\n", " ")
