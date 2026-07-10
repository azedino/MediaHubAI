"""Seleção explicável de cortes com sinais linguísticos, ritmo e mudanças de cena."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from core.models import ClipCandidate, TranscriptSegment


@dataclass(frozen=True, slots=True)
class _ScoredWindow:
    candidate: ClipCandidate
    speech_coverage: float


class ViralClipAnalyzer:
    """Rankeador heurístico local; não promete viralização nem envia dados à nuvem."""

    HOOK_TERMS = {
        "voce sabia",
        "como fazer",
        "por que",
        "o segredo",
        "ninguem te conta",
        "pare de",
        "nunca faca",
        "presta atencao",
        "olha isso",
        "imagine",
        "a verdade",
        "o maior erro",
        "em segundos",
        "passo a passo",
    }
    EMOTION_TERMS = {
        "incrivel",
        "absurdo",
        "surpreendente",
        "chocante",
        "genial",
        "erro",
        "medo",
        "amor",
        "odio",
        "segredo",
        "resultado",
        "dinheiro",
        "melhor",
        "pior",
        "impossivel",
    }

    def analyze(
        self,
        segments: list[TranscriptSegment],
        *,
        media_duration: float,
        target_duration: float,
        count: int,
        scene_changes: list[float] | None = None,
    ) -> list[ClipCandidate]:
        duration = max(1.0, min(target_duration, media_duration))
        scenes = sorted(scene_changes or [])
        if not segments:
            return self._timeline_candidates(media_duration, duration, count, scenes)

        anchors = {0.0, max(0.0, media_duration - duration)}
        for segment in segments:
            anchors.add(max(0.0, segment.start - min(2.0, duration * 0.08)))
        for scene_time in scenes:
            anchors.add(max(0.0, scene_time - duration * 0.15))

        scored = [
            self._score_window(
                start=min(anchor, max(0.0, media_duration - duration)),
                duration=duration,
                segments=segments,
                scenes=scenes,
                media_duration=media_duration,
            )
            for anchor in anchors
        ]
        scored.sort(key=lambda item: (item.candidate.score, item.speech_coverage), reverse=True)

        selected: list[ClipCandidate] = []
        for item in scored:
            candidate = item.candidate
            if any(self._overlap_ratio(candidate, existing) > 0.42 for existing in selected):
                continue
            selected.append(candidate)
            if len(selected) == count:
                break

        if len(selected) < count:
            fallbacks = self._timeline_candidates(media_duration, duration, count * 2, scenes)
            for candidate in fallbacks:
                if any(self._overlap_ratio(candidate, existing) > 0.70 for existing in selected):
                    continue
                selected.append(candidate)
                if len(selected) == count:
                    break

        return selected[:count]

    def _score_window(
        self,
        *,
        start: float,
        duration: float,
        segments: list[TranscriptSegment],
        scenes: list[float],
        media_duration: float,
    ) -> _ScoredWindow:
        end = min(media_duration, start + duration)
        included = [segment for segment in segments if segment.end > start and segment.start < end]
        raw_text = " ".join(segment.text for segment in included).strip()
        normalized = self._normalize(raw_text)
        words = re.findall(r"\b[\wÀ-ÿ]+\b", raw_text)
        window_duration = max(1.0, end - start)
        spoken_seconds = sum(
            max(0.0, min(segment.end, end) - max(segment.start, start)) for segment in included
        )
        coverage = min(1.0, spoken_seconds / window_duration)
        words_per_second = len(words) / window_duration
        pace_score = max(0.0, 1.0 - abs(words_per_second - 2.7) / 2.7)

        hook_hits = [term for term in self.HOOK_TERMS if term in normalized]
        emotion_hits = [term for term in self.EMOTION_TERMS if term in normalized]
        has_question = "?" in raw_text or normalized.startswith(("como ", "por que ", "qual "))
        has_number = bool(re.search(r"\b\d+(?:[.,]\d+)?\b", raw_text))
        scene_count = sum(start <= value <= end for value in scenes)
        scene_score = min(1.0, scene_count / max(2.0, window_duration / 12.0))
        complete_ending = raw_text.endswith((".", "!", "?"))

        score = 24.0
        score += min(20.0, len(hook_hits) * 10.0)
        score += min(12.0, len(emotion_hits) * 3.0)
        score += 8.0 if has_question else 0.0
        score += 5.0 if has_number else 0.0
        score += pace_score * 10.0
        score += coverage * 11.0
        score += scene_score * 7.0
        score += 3.0 if complete_ending else 0.0
        score = round(min(100.0, score), 1)

        reasons: list[str] = []
        if hook_hits:
            reasons.append("gancho forte")
        if has_question:
            reasons.append("abre curiosidade")
        if emotion_hits:
            reasons.append("linguagem emocional")
        if pace_score >= 0.72:
            reasons.append("ritmo de fala envolvente")
        if scene_score >= 0.55:
            reasons.append("boa dinâmica visual")
        if not reasons:
            reasons.append("trecho contínuo com boa densidade")

        title_words = words[:9]
        title = " ".join(title_words).strip()
        if len(words) > 9:
            title += "…"
        if not title:
            title = f"Corte em {self._clock(start)}"

        return _ScoredWindow(
            ClipCandidate(start, end, score, title, tuple(reasons)),
            coverage,
        )

    def _timeline_candidates(
        self,
        media_duration: float,
        duration: float,
        count: int,
        scenes: list[float],
    ) -> list[ClipCandidate]:
        if media_duration <= duration:
            starts = [0.0]
        else:
            usable = media_duration - duration
            starts = [usable * (index + 1) / (count + 1) for index in range(count)]
            if scenes:
                starts = [
                    max(0.0, min(media_duration - duration, self._nearest_scene(value, scenes)))
                    for value in starts
                ]
        unique_starts: list[float] = []
        for value in starts:
            if not any(abs(value - existing) < 0.5 for existing in unique_starts):
                unique_starts.append(value)
        return [
            ClipCandidate(
                start=round(start, 3),
                end=round(min(media_duration, start + duration), 3),
                score=40.0,
                title=f"Corte automático {index}",
                reasons=("distribuição temporal", "mudança de cena próxima" if scenes else "fallback local"),
            )
            for index, start in enumerate(unique_starts, 1)
        ]

    @staticmethod
    def _nearest_scene(target: float, scenes: list[float]) -> float:
        nearest = min(scenes, key=lambda value: abs(value - target))
        return nearest if abs(nearest - target) <= 8.0 else target

    @staticmethod
    def _overlap_ratio(left: ClipCandidate, right: ClipCandidate) -> float:
        intersection = max(0.0, min(left.end, right.end) - max(left.start, right.start))
        return intersection / max(1.0, min(left.duration, right.duration))

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.lower())
        return "".join(character for character in decomposed if not unicodedata.combining(character))

    @staticmethod
    def _clock(seconds: float) -> str:
        minutes, seconds = divmod(int(math.floor(seconds)), 60)
        return f"{minutes:02d}:{seconds:02d}"
