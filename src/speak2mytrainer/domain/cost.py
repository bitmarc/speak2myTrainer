"""Costo estimado de un intento en USD, calculado en Python con el uso real de cada servicio.

Solo cuenta lo que se paga: el recurso F0 de Speech es gratis dentro de sus 5 h al mes, así
que una pasada atendida por F0 cuesta 0. Los precios son configuración (cambian con el modelo
o la región); los valores por defecto son los del PRD, East US 2, 13-nov-2026.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prices:
    llm_input_per_million: float = 0.40  # gpt-4.1-mini
    llm_output_per_million: float = 1.60
    transcribe_per_minute: float = 0.003  # gpt-4o-mini-transcribe
    speech_per_hour: float = 1.0  # STT estándar en S0, por pasada
    tts_per_million_chars: float = 15.0  # TTS neural en S0


@dataclass(frozen=True)
class Usage:
    transcribe_sec: float = 0.0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    speech_paid_sec: float = 0.0  # segundos de audio que procesó el recurso de pago
    tts_paid_chars: int = 0


def estimate(usage: Usage, prices: Prices) -> float:
    cost = (
        usage.llm_input_tokens * prices.llm_input_per_million / 1_000_000
        + usage.llm_output_tokens * prices.llm_output_per_million / 1_000_000
        + usage.transcribe_sec / 60 * prices.transcribe_per_minute
        + usage.speech_paid_sec / 3600 * prices.speech_per_hour
        + usage.tts_paid_chars * prices.tts_per_million_chars / 1_000_000
    )
    return round(cost, 6)
