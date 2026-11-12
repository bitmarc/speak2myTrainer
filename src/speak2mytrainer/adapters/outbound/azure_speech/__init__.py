"""Adaptador `SpeechRecognizer` con el Speech SDK: forma léxica y marcas de tiempo (ADR 0002)."""

from __future__ import annotations

import json
import threading
import wave
from pathlib import Path
from typing import Any

import azure.cognitiveservices.speech as speechsdk
from azure.core.credentials import TokenCredential

from speak2mytrainer.application.ports import RecognitionResult
from speak2mytrainer.domain.errors import ServiceQuotaError
from speak2mytrainer.domain.models import TimedWord, VerbatimTranscript

_SCOPE = "https://cognitiveservices.azure.com/.default"
_TICKS_PER_SEC = 10_000_000  # el SDK mide offsets en unidades de 100 ns
_LOCALES = {"en": "en-US"}


class AzureSpeechRecognizer:
    def __init__(self, credential: TokenCredential, resource_id: str, region: str) -> None:
        self._credential = credential
        self._resource_id = resource_id
        self._region = region

    def _config(self, language: str) -> speechsdk.SpeechConfig:
        # Sin llaves: token de Entra con el formato `aad#{resourceId}#{token}`. Se pide uno
        # nuevo por intento porque caduca en una hora.
        token = self._credential.get_token(_SCOPE).token
        config = speechsdk.SpeechConfig(
            auth_token=f"aad#{self._resource_id}#{token}", region=self._region
        )
        config.speech_recognition_language = _LOCALES.get(language, language)
        config.output_format = speechsdk.OutputFormat.Detailed
        config.request_word_level_timestamps()
        return config

    def recognize(
        self, wav_path: Path, language: str, assess_pronunciation: bool = False
    ) -> RecognitionResult:
        if assess_pronunciation:
            raise NotImplementedError("La evaluación de pronunciación llega en la Fase 2.")
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=self._config(language),
            audio_config=speechsdk.audio.AudioConfig(filename=str(wav_path)),
        )
        segments = _run_continuous(recognizer, timeout_sec=_timeout(wav_path))

        words: list[TimedWord] = []
        lexical: list[str] = []
        for segment in segments:
            best = (segment.get("NBest") or [{}])[0]
            if best.get("Lexical"):
                lexical.append(best["Lexical"])
            for w in best.get("Words", []):
                start = w["Offset"] / _TICKS_PER_SEC
                words.append(
                    TimedWord(
                        text=w["Word"],
                        start_sec=round(start, 2),
                        end_sec=round(start + w["Duration"] / _TICKS_PER_SEC, 2),
                    )
                )
        return RecognitionResult(
            verbatim=VerbatimTranscript(lexical=" ".join(lexical), words=words)
        )


def _timeout(wav_path: Path) -> float:
    """Speech procesa a ~0.5x tiempo real; se da margen de 2x la duración, mínimo 2 min."""
    with wave.open(str(wav_path)) as w:
        seconds: float = w.getnframes() / w.getframerate()
    return max(120.0, 2 * seconds)


def _run_continuous(recognizer: speechsdk.SpeechRecognizer, timeout_sec: float) -> list[Any]:
    """Reconocimiento continuo (sin el límite de 30 s). Devuelve el JSON de cada segmento."""
    done = threading.Event()
    segments: list[Any] = []
    errors: list[tuple[str, str]] = []

    def on_recognized(evt: Any) -> None:
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            raw = evt.result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
            segments.append(json.loads(raw))

    def on_canceled(evt: Any) -> None:
        details = evt.cancellation_details
        if details.reason == speechsdk.CancellationReason.Error:
            errors.append((str(details.error_code), details.error_details or ""))
        done.set()

    recognizer.recognized.connect(on_recognized)
    recognizer.canceled.connect(on_canceled)
    recognizer.session_stopped.connect(lambda _: done.set())
    recognizer.start_continuous_recognition()
    finished = done.wait(timeout_sec)
    recognizer.stop_continuous_recognition()

    if not finished:
        raise TimeoutError(f"Speech no terminó en {timeout_sec:.0f} s.")
    if errors:
        code, details = errors[0]
        # F0 rechaza solicitudes al agotar sus 5 horas del mes.
        if "TooManyRequests" in code or "quota" in details.lower():
            raise ServiceQuotaError(
                "Se agotaron por este mes los minutos gratuitos de reconocimiento de voz. "
                "Avísale al admin."
            )
        raise RuntimeError(f"Speech canceló el reconocimiento: {code}: {details}")
    return segments
