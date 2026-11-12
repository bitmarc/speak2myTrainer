from datetime import UTC, datetime

import pytest

from speak2mytrainer.domain.errors import InvalidStatusTransitionError
from speak2mytrainer.domain.models import Attempt, AttemptStatus, Quota


def make_attempt() -> Attempt:
    return Attempt(
        id="a1", user_id="u@x.com", practice_id="p1", number=1, audio_blob="x", duration_sec=60
    )


def test_happy_path_with_pronunciation() -> None:
    attempt = make_attempt()
    for status in ("transcribing", "assessing", "analyzing", "done"):
        attempt.advance(AttemptStatus(status))
    assert attempt.status is AttemptStatus.DONE


def test_assessing_is_optional() -> None:
    attempt = make_attempt()
    attempt.advance(AttemptStatus.TRANSCRIBING)
    attempt.advance(AttemptStatus.ANALYZING)
    attempt.advance(AttemptStatus.DONE)
    assert attempt.status is AttemptStatus.DONE


def test_cannot_skip_to_done() -> None:
    attempt = make_attempt()
    with pytest.raises(InvalidStatusTransitionError):
        attempt.advance(AttemptStatus.DONE)


def test_failed_keeps_error_and_can_requeue() -> None:
    attempt = make_attempt()
    attempt.advance(AttemptStatus.TRANSCRIBING)
    attempt.advance(AttemptStatus.FAILED, error="timeout")
    assert attempt.error == "timeout"
    attempt.advance(AttemptStatus.QUEUED)
    assert attempt.error is None


def test_done_cannot_fail() -> None:
    attempt = make_attempt()
    for status in ("transcribing", "analyzing", "done"):
        attempt.advance(AttemptStatus(status))
    with pytest.raises(InvalidStatusTransitionError):
        attempt.advance(AttemptStatus.FAILED)


def test_quota_allows_and_consumes() -> None:
    quota = Quota(minutes_per_month=10, period_start=datetime(2026, 11, 1, tzinfo=UTC))
    assert quota.allows(600)
    quota.consume(540)
    assert quota.remaining_minutes() == 1
    assert not quota.allows(61)


def test_quota_rolls_over_in_new_month() -> None:
    quota = Quota(
        minutes_per_month=10, used_this_month=10, period_start=datetime(2026, 11, 1, tzinfo=UTC)
    )
    quota.roll_over_if_needed(datetime(2026, 11, 30, tzinfo=UTC))
    assert quota.used_this_month == 10
    quota.roll_over_if_needed(datetime(2026, 12, 3, 15, tzinfo=UTC))
    assert quota.used_this_month == 0
    assert quota.period_start == datetime(2026, 12, 1, tzinfo=UTC)
