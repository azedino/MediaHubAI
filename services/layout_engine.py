"""FFmpeg layout generation for professional 1080x1920 shorts."""

from __future__ import annotations

from dataclasses import dataclass

from core.models import MediaInfo, ReactionAnalysis, ShortTemplate

from .geometry import BoundingBox
from .shorts_config import LayoutConfig, RenderConfig


@dataclass(frozen=True, slots=True)
class LayoutRegions:
    webcam: BoundingBox | None
    gameplay: BoundingBox
    captions: BoundingBox


class LayoutEngine:
    def __init__(
        self,
        render_config: RenderConfig | None = None,
        layout_config: LayoutConfig | None = None,
    ) -> None:
        self._render = render_config or RenderConfig()
        self._layout = layout_config or LayoutConfig()

    def regions(self, reaction: ReactionAnalysis) -> LayoutRegions:
        width = self._render.width
        height = self._render.height
        caption_height = self._even(round(height * self._layout.caption_height_ratio))
        webcam_height = (
            self._even(round(height * self._layout.webcam_height_ratio)) if reaction.detected else 0
        )
        caption_y = height - caption_height
        gameplay_y = webcam_height + (self._layout.gutter if webcam_height else 0)
        gameplay_height = max(2, caption_y - gameplay_y - self._layout.gutter)
        gameplay_height = self._even(gameplay_height)
        webcam = BoundingBox(0, 0, width, webcam_height) if webcam_height else None
        gameplay = BoundingBox(0, gameplay_y, width, gameplay_height)
        captions = BoundingBox(0, caption_y, width, caption_height)
        return LayoutRegions(webcam=webcam, gameplay=gameplay, captions=captions)

    def build(
        self,
        *,
        media: MediaInfo,
        template: ShortTemplate,
        reaction: ReactionAnalysis,
    ) -> str:
        del template
        regions = self.regions(reaction)
        source_box = reaction.webcam_box or reaction.face_box
        if reaction.detected and source_box and regions.webcam:
            webcam_source = BoundingBox.from_tuple(source_box).clamp(media.width, media.height)
            return self._stacked_reaction_layout(webcam_source, regions)
        return self._gameplay_only_layout(regions)

    def _stacked_reaction_layout(self, webcam_source: BoundingBox, regions: LayoutRegions) -> str:
        assert regions.webcam is not None
        return (
            "[0:v]split=3[bgsrc][gamesrc][facesrc];"
            f"{self._background('[bgsrc]')}[bg];"
            f"[facesrc]crop={webcam_source.width}:{webcam_source.height}:{webcam_source.x}:{webcam_source.y},"
            f"{self._fit(regions.webcam.width, regions.webcam.height)}[web];"
            f"[gamesrc]{self._fit(regions.gameplay.width, regions.gameplay.height)}[game];"
            "[bg][web]overlay=0:0[stage1];"
            f"[stage1][game]overlay={regions.gameplay.x}:{regions.gameplay.y}[stage2];"
            f"[stage2]{self._caption_band(regions.captions)}[layout]"
        )

    def _gameplay_only_layout(self, regions: LayoutRegions) -> str:
        return (
            "[0:v]split=2[bgsrc][gamesrc];"
            f"{self._background('[bgsrc]')}[bg];"
            f"[gamesrc]{self._fit(regions.gameplay.width, self._gameplay_extent(regions))}[game];"
            "[bg][game]overlay=0:0[stage1];"
            f"[stage1]{self._caption_band(regions.captions)}[layout]"
        )

    def _background(self, label: str) -> str:
        return (
            f"{label}scale={self._render.width}:{self._render.height}:force_original_aspect_ratio=increase,"
            f"crop={self._render.width}:{self._render.height},gblur=sigma={self._layout.background_blur},"
            "eq=saturation=0.92:brightness=-0.035"
        )

    @staticmethod
    def _fit(width: int, height: int) -> str:
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
        )

    def _caption_band(self, captions: BoundingBox) -> str:
        alpha = max(0.0, min(1.0, self._layout.bottom_dim_alpha))
        return (
            f"drawbox=x={captions.x}:y={captions.y}:w={captions.width}:h={captions.height}:"
            f"color=black@{alpha:.2f}:t=fill"
        )

    @staticmethod
    def _gameplay_extent(regions: LayoutRegions) -> int:
        return regions.gameplay.y + regions.gameplay.height

    @staticmethod
    def _even(value: int) -> int:
        return max(2, value // 2 * 2)
