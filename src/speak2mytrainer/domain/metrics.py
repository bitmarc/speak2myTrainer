"""Métricas deterministas. Python hace los números; el LLM solo clasifica, explica y reescribe."""

from __future__ import annotations

import re

from speak2mytrainer.domain.errors import AudioDurationError
from speak2mytrainer.domain.models import (
    Filler,
    FillerType,
    Metrics,
    PronunciationAssessment,
    VerbatimTranscript,
)

MIN_DURATION_SEC = 10.0
MAX_DURATION_SEC = 600.0

# Referencia de ritmo para una entrevista (PRD, bloque de métricas).
INTERVIEW_WPM_RANGE = (120, 150)

_APOSTROPHES = "'\N{RIGHT SINGLE QUOTATION MARK}"
_WORD_RE = re.compile(rf"[A-Za-zÀ-ÿ0-9]+(?:[{_APOSTROPHES}][A-Za-zÀ-ÿ]+)*")


def validate_duration(duration_sec: float) -> None:
    if duration_sec < MIN_DURATION_SEC:
        raise AudioDurationError(
            f"El audio dura {duration_sec:.0f} s; el mínimo es {MIN_DURATION_SEC:.0f} s."
        )
    if duration_sec > MAX_DURATION_SEC:
        raise AudioDurationError(
            f"El audio dura {duration_sec / 60:.1f} min; el máximo es "
            f"{MAX_DURATION_SEC / 60:.0f} min."
        )


def count_words(transcript: str) -> int:
    """Cuenta palabras habladas, incluidas las muletillas: todas ocupan tiempo de habla."""
    return len(_WORD_RE.findall(transcript))


def compute_wpm(words: int, duration_sec: float) -> float:
    if duration_sec <= 0:
        return 0.0
    return round(words / (duration_sec / 60), 1)


def fillers_per_minute(fillers: list[Filler], duration_sec: float) -> float:
    if duration_sec <= 0:
        return 0.0
    return round(len(fillers) / (duration_sec / 60), 2)


def count_restarts(fillers: list[Filler]) -> int:
    return sum(1 for f in fillers if f.type is FillerType.RESTART)


def build_metrics(
    transcript: str,
    duration_sec: float,
    fillers: list[Filler],
    verbatim: VerbatimTranscript | None = None,
    pronunciation: PronunciationAssessment | None = None,
) -> Metrics:
    """Con la transcripción verbatim, las palabras salen de la forma léxica (incluye muletillas) y
    el ritmo se mide sobre el tiempo de habla, sin silencios al inicio ni al final. Los puntajes
    de pronunciación se copian tal cual de Speech."""
    words = count_words(verbatim.lexical if verbatim else transcript)
    speaking = (verbatim.speaking_span_sec() if verbatim else None) or duration_sec
    return Metrics(
        duration_sec=round(duration_sec, 1),
        words=words,
        wpm=compute_wpm(words, speaking),
        fillers_per_min=fillers_per_minute(fillers, speaking),
        restarts=count_restarts(fillers),
        pron_score=pronunciation.pron_score if pronunciation else None,
        accuracy=pronunciation.accuracy if pronunciation else None,
        fluency=pronunciation.fluency if pronunciation else None,
        prosody=pronunciation.prosody if pronunciation else None,
    )
