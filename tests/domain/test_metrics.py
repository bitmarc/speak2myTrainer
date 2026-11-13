import pytest

from speak2mytrainer.domain.errors import AudioDurationError
from speak2mytrainer.domain.metrics import (
    build_metrics,
    compute_wpm,
    count_words,
    fillers_per_minute,
    validate_duration,
)
from speak2mytrainer.domain.models import Filler, FillerType, TimedWord, VerbatimTranscript


def test_count_words_includes_fillers_and_contractions() -> None:
    assert count_words("well um I'm gonna build a eemm a system") == 9


def test_count_words_handles_curly_apostrophe() -> None:
    assert count_words("I\N{RIGHT SINGLE QUOTATION MARK}m done") == 2


def test_count_words_ignores_punctuation() -> None:
    assert count_words("So... the client — needed users, roles!") == 6


def test_compute_wpm() -> None:
    assert compute_wpm(words=130, duration_sec=60) == 130.0
    assert compute_wpm(words=65, duration_sec=30) == 130.0


def test_compute_wpm_zero_duration() -> None:
    assert compute_wpm(words=10, duration_sec=0) == 0.0


def test_fillers_per_minute() -> None:
    fillers = [Filler(quote="eemm", token="eemm", type=FillerType.HESITATION)] * 3
    assert fillers_per_minute(fillers, duration_sec=120) == 1.5


@pytest.mark.parametrize("seconds", [10, 60, 600])
def test_validate_duration_accepts_range(seconds: float) -> None:
    validate_duration(seconds)


@pytest.mark.parametrize("seconds", [0, 9.9, 600.1, 3600])
def test_validate_duration_rejects_out_of_range(seconds: float) -> None:
    with pytest.raises(AudioDurationError):
        validate_duration(seconds)


def test_build_metrics_counts_restarts() -> None:
    fillers = [
        Filler(quote="we build a eemm a system", token="eemm", type=FillerType.HESITATION),
        Filler(quote="to helps retrieve", token="to helps", type=FillerType.RESTART),
    ]
    metrics = build_metrics("one two three four five six", duration_sec=30, fillers=fillers)
    assert metrics.words == 6
    assert metrics.wpm == 12.0
    assert metrics.fillers_per_min == 4.0
    assert metrics.restarts == 1


def test_build_metrics_uses_verbatim_words_and_speaking_time() -> None:
    # 4 palabras léxicas (con el "um") entre 1.0 s y 3.0 s, en un audio de 12 s.
    verbatim = VerbatimTranscript(
        lexical="so um we built",
        words=[
            TimedWord(text=w, start_sec=1.0 + i * 0.5, end_sec=1.5 + i * 0.5)
            for i, w in enumerate(["so", "um", "we", "built"])
        ],
    )
    fillers = [Filler(quote="so um we", token="um", type=FillerType.HESITATION)]
    metrics = build_metrics("So we built.", 12.0, fillers, verbatim)
    assert metrics.duration_sec == 12.0
    assert metrics.words == 4
    assert metrics.wpm == 120.0
    assert metrics.fillers_per_min == 30.0


def test_build_metrics_copies_pronunciation_scores() -> None:
    from speak2mytrainer.domain.models import PronunciationAssessment

    pa = PronunciationAssessment(pron_score=84.0, accuracy=90.9, fluency=90.8, prosody=None)
    metrics = build_metrics("one two three", 60, [], pronunciation=pa)
    assert (metrics.pron_score, metrics.accuracy, metrics.fluency, metrics.prosody) == (
        84.0,
        90.9,
        90.8,
        None,
    )
