from core.models import TranscriptSegment
from services.viral_analyzer import ViralClipAnalyzer


def test_strong_hook_is_ranked_above_neutral_speech() -> None:
    segments = [
        TranscriptSegment("Hoje vamos continuar nossa conversa normal.", 5, 12),
        TranscriptSegment("Você sabia o segredo que ninguém te conta?", 48, 54),
        TranscriptSegment("O resultado é incrível: três vezes mais rápido!", 54, 61),
        TranscriptSegment("Agora voltamos ao assunto anterior.", 90, 96),
    ]
    candidates = ViralClipAnalyzer().analyze(
        segments,
        media_duration=120,
        target_duration=18,
        count=2,
        scene_changes=[49, 52, 58],
    )
    assert candidates
    assert candidates[0].start <= 54 <= candidates[0].end
    assert candidates[0].score > 60
    assert "gancho forte" in candidates[0].reasons


def test_fallback_distributes_clips_without_transcript() -> None:
    candidates = ViralClipAnalyzer().analyze(
        [], media_duration=100, target_duration=20, count=3, scene_changes=[]
    )
    assert len(candidates) == 3
    assert all(candidate.duration == 20 for candidate in candidates)
