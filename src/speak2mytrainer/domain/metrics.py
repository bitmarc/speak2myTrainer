"""Métricas deterministas. Python hace los números; el LLM solo clasifica, explica y reescribe."""

from __future__ import annotations

import re

from speak2mytrainer.domain.errors import AudioDurationError
from speak2mytrainer.domain.models import Filler, FillerType, Metrics

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


def build_metrics(transcript: str, duration_sec: float, fillers: list[Filler]) -> Metrics:
    words = count_words(transcript)
    return Metrics(
        duration_sec=round(duration_sec, 1),
        words=words,
        wpm=compute_wpm(words, duration_sec),
        fillers_per_min=fillers_per_minute(fillers, duration_sec),
        restarts=count_restarts(fillers),
    )
