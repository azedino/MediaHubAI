"""FFmpeg renderer for short clips."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from core.errors import InvalidMediaError
from core.models import FilterPreset, MediaInfo, ReactionAnalysis, ShortTemplate

from .ffmpeg import EncoderProfile, FFmpegService
from .layout_engine import LayoutEngine
from .shorts_config import RenderConfig

ProgressCallback = Callable[[float, str], None]


FILTER_CHAINS: dict[FilterPreset, str] = {
    FilterPreset.NONE: "",
    FilterPreset.VIBRANT: "eq=saturation=1.20:contrast=1.05:brightness=0.012",
    FilterPreset.CINEMATIC: "eq=saturation=0.90:contrast=1.12:gamma=0.97,vignette=PI/5",
    FilterPreset.WARM: "colorbalance=rs=.055:gs=.020:bs=-.035,eq=saturation=1.07",
    FilterPreset.COOL: "colorbalance=rs=-.035:gs=.008:bs=.060,eq=saturation=1.04",
    FilterPreset.BLACK_AND_WHITE: "hue=s=0,eq=contrast=1.10",
}


class ShortRenderer:
    def __init__(
        self,
        ffmpeg: FFmpegService,
        *,
        render_config: RenderConfig | None = None,
        layout_engine: LayoutEngine | None = None,
    ) -> None:
        self._ffmpeg = ffmpeg
        self._render = render_config or RenderConfig()
        self._layout_engine = layout_engine or LayoutEngine(self._render)

    def render(
        self,
        *,
        media: MediaInfo,
        start: float,
        duration: float,
        output: Path,
        speed: float,
        mirror: bool,
        filter_preset: FilterPreset,
        template: ShortTemplate,
        reaction: ReactionAnalysis,
        subtitle_path: Path | None,
        cancel_event: threading.Event,
        progress_callback: ProgressCallback | None,
        execution_device: str = "auto",
    ) -> None:
        filter_graph = self.build_filter_graph(
            media=media,
            width=self._render.width,
            height=self._render.height,
            speed=speed,
            mirror=mirror,
            filter_preset=filter_preset,
            template=template,
            reaction=reaction,
            subtitle_path=subtitle_path,
        )
        encoder = self._ffmpeg.select_h264_encoder(execution_device)
        expected_duration = max(0.1, duration / speed)
        arguments = self._build_arguments(
            media=media,
            start=start,
            duration=duration,
            output=output,
            filter_graph=filter_graph,
            encoder=encoder,
        )
        try:
            self._ffmpeg.run(
                arguments,
                expected_duration=expected_duration,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
        except InvalidMediaError:
            if encoder.name == "libx264":
                raise
            if output.exists():
                output.unlink()
            fallback = EncoderProfile("libx264", ("-preset", "veryfast", "-crf", "18"), "cpu", False)
            fallback_arguments = self._build_arguments(
                media=media,
                start=start,
                duration=duration,
                output=output,
                filter_graph=filter_graph,
                encoder=fallback,
            )
            if progress_callback:
                progress_callback(0.0, f"{encoder.name} failed; retrying with CPU encoder")
            self._ffmpeg.run(
                fallback_arguments,
                expected_duration=expected_duration,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )

    def _build_arguments(
        self,
        *,
        media: MediaInfo,
        start: float,
        duration: float,
        output: Path,
        filter_graph: str,
        encoder: EncoderProfile,
    ) -> list[str | Path]:
        arguments: list[str | Path] = [
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            media.path,
            "-filter_complex",
            filter_graph,
            "-map",
            "[vout]",
        ]
        if media.has_audio:
            arguments.extend(["-map", "[aout]"])
        else:
            arguments.append("-an")
        arguments.extend(["-c:v", encoder.name, *encoder.args, "-pix_fmt", "yuv420p"])
        if media.has_audio:
            arguments.extend(["-c:a", "aac", "-b:a", self._render.audio_bitrate])
        arguments.extend(["-movflags", "+faststart", "-shortest", output])
        return arguments

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
        layout_engine = self._layout_engine
        if width != self._render.width or height != self._render.height:
            layout_engine = LayoutEngine(RenderConfig(width=width, height=height))
        layout = layout_engine.build(media=media, template=template, reaction=reaction)
        final_filters = [f"setpts=PTS/{speed:.6f}"]
        if mirror:
            final_filters.append("hflip")
        color_filter = FILTER_CHAINS[filter_preset]
        if color_filter:
            final_filters.extend(color_filter.split(","))
        if subtitle_path:
            escaped_path = self.escape_filter_path(subtitle_path)
            final_filters.append(f"ass=filename='{escaped_path}'")
        final_filters.extend(["setsar=1", "format=yuv420p"])
        graph = layout + ";[layout]" + ",".join(final_filters) + "[vout]"
        if media.has_audio:
            graph += (
                f";[0:a]atempo={speed:.6f},"
                f"loudnorm=I={self._render.target_lufs}:TP=-1.5:LRA=11[aout]"
            )
        return graph

    @staticmethod
    def escape_filter_path(path: Path) -> str:
        value = path.resolve().as_posix()
        return (
            value.replace("\\", "/")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace(",", "\\,")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )
