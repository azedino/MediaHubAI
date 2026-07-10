from pathlib import Path

from core.models import CaptionPreset, TranscriptSegment, TranscriptWord
from services.captions import CaptionRenderer


def test_ass_caption_contains_karaoke_and_clipped_timestamps(tmp_path: Path) -> None:
    segment = TranscriptSegment(
        "Este corte começa agora",
        10,
        13,
        (
            TranscriptWord("Este", 10, 10.4),
            TranscriptWord("corte", 10.4, 11),
            TranscriptWord("começa", 11, 12),
            TranscriptWord("agora", 12, 13),
        ),
    )
    output = CaptionRenderer().write_ass(
        [segment],
        tmp_path / "legenda.ass",
        clip_start=10,
        clip_end=13,
        width=1080,
        height=1920,
        preset=CaptionPreset.VIRAL,
        font_name="Arial",
    )
    content = output.read_text(encoding="utf-8-sig")
    assert "PlayResX: 1080" in content
    assert "Dialogue: 0,0:00:00.00" in content
    assert "{\\kf" in content
    assert "AGORA" in content
