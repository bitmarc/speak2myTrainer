import pytest

from speak2mytrainer.domain.cost import Prices, Usage, estimate


def test_estimate_adds_every_paid_service() -> None:
    usage = Usage(
        transcribe_sec=120,  # 2 min a 0.003
        llm_input_tokens=5_000,  # 0.002
        llm_output_tokens=2_500,  # 0.004
        speech_paid_sec=1_800,  # media hora en S0
        tts_paid_chars=1_000,  # 0.015
    )
    assert estimate(usage, Prices()) == pytest.approx(0.006 + 0.002 + 0.004 + 0.5 + 0.015)


def test_free_tier_costs_nothing() -> None:
    # F0 atendió Speech y TTS: solo se paga la transcripción y el LLM.
    assert estimate(Usage(), Prices()) == 0
    assert estimate(Usage(transcribe_sec=60), Prices()) == pytest.approx(0.003)


def test_prices_are_configuration() -> None:
    assert estimate(Usage(llm_input_tokens=1_000_000), Prices(llm_input_per_million=2.0)) == 2.0
