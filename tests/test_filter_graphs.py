from pathlib import Path

import pytest

from core.models import FilterPreset, MediaInfo, ReactionAnalysis, ShortTemplate
from services.short_creator import ShortCreationService


@pytest.mark.parametrize(
    "template,expected",
    [
        (ShortTemplate.FILL, "force_original_aspect_ratio=increase"),
        (ShortTemplate.BLUR_BACKGROUND, "gblur=sigma=28"),
        (ShortTemplate.REACTION_TOP, "[facesrc]crop="),
        (ShortTemplate.REACTION_BOTTOM, "[facesrc]crop="),
        (ShortTemplate.SPLIT, "[facesrc]crop="),
    ],
)
def test_filter_graphs_are_labeled_and_mapped(template: ShortTemplate, expected: str) -> None:
    service = object.__new__(ShortCreationService)
    media = MediaInfo(Path("sample.mp4"), 60, 1920, 1080, True)
    graph = service.build_filter_graph(
        media=media,
        width=1080,
        height=1920,
        speed=1.25,
        mirror=True,
        filter_preset=FilterPreset.VIBRANT,
        template=template,
        reaction=ReactionAnalysis(True, 0.8, (1500, 50, 240, 240), "test"),
        subtitle_path=None,
    )
    assert expected in graph
    assert "hflip" in graph
    assert "setpts=PTS/1.250000" in graph
    assert graph.endswith("[aout]")
