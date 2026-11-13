"""Adaptadores `SpeechRecognizer` y `SpeechSynthesizer` con el Speech SDK.

Una sola pasada de reconocimiento continuo da la forma léxica con marcas de tiempo (ADR 0002) y,
si se pide, la evaluación de pronunciación no guionizada (ADR 0003).

Los recursos de Speech van en orden (F0 primero, S0 de respaldo): si uno rechaza por cuota o
concurrencia, la misma solicitud se repite en el siguiente.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import azure.cognitiveservices.speech as speechsdk
from azure.core.credentials import TokenCredential

from speak2mytrainer.application.ports import RecognitionResult
from speak2mytrainer.domain.errors import ServiceQuotaError
from speak2mytrainer.domain.models import (
    PronunciationAssessment,
    PronunciationIssue,
    TimedWord,
    VerbatimTranscript,
    VoiceGender,
)

_SCOPE = "https://cognitiveservices.azure.com/.default"
_TICKS_PER_SEC = 10_000_000  # el SDK mide offsets en unidades de 100 ns
_LOCALES = {"en": "en-US"}
_PROSODY_LOCALES = {"en-US"}  # la prosodia solo existe en inglés de EE. UU.
_LOW_SCORE = 60.0  # precisión por debajo de la cual una palabra o un fonema se marca
_COOLDOWN_SEC = 600  # tras un rechazo, el recurso se salta durante 10 min

_log = logging.getLogger(__name__)
_T = TypeVar("_T")


@dataclass(frozen=True)
class SpeechResource:
    resource_id: str
    region: str


class _Failover:
    """Prueba los recursos en orden. El que rechaza por cuota se salta un rato, para no pagar
    un intento fallido en cada solicitud cuando F0 ya agotó el mes."""

    def __init__(self, resources: Sequence[SpeechResource]) -> None:
        if not resources:
            raise ValueError("Se necesita al menos un recurso de Speech.")
        self._resources = list(resources)
        self._skip_until = [0.0] * len(self._resources)

    def run(self, call: Callable[[SpeechResource], _T]) -> _T:
        now = time.monotonic()
        order = [i for i in range(len(self._resources)) if self._skip_until[i] <= now]
        # Si todos están en pausa, se intenta igual con todos: quizá ya se recuperaron.
        order = order or list(range(len(self._resources)))
        error: ServiceQuotaError | None = None
        for i in order:
            resource = self._resources[i]
            try:
                result = call(resource)
            except ServiceQuotaError as exc:
                self._skip_until[i] = time.monotonic() + _COOLDOWN_SEC
                _log.warning("Speech rechazó la solicitud en %s: %s", _name(resource), exc)
                error = exc
                continue
            if i != 0:
                _log.warning("Speech respondió con el recurso de respaldo %s", _name(resource))
            return result
        assert error is not None
        raise error


def _name(resource: SpeechResource) -> str:
    return resource.resource_id.rsplit("/", 1)[-1]


def speech_config(credential: TokenCredential, resource: SpeechResource) -> speechsdk.SpeechConfig:
    # Sin llaves: token de Entra con el formato `aad#{resourceId}#{token}`. Se pide uno nuevo
    # por solicitud porque caduca en una hora.
    token = credential.get_token(_SCOPE).token
    return speechsdk.SpeechConfig(
        auth_token=f"aad#{resource.resource_id}#{token}", region=resource.region
    )


_SCORES = {
    "pron_score": "PronScore",
    "accuracy": "AccuracyScore",
    "fluency": "FluencyScore",
    "prosody": "ProsodyScore",
}


class AzureSpeechRecognizer:
    def __init__(self, credential: TokenCredential, resources: Sequence[SpeechResource]) -> None:
        self._credential = credential
        self._failover = _Failover(resources)

    def recognize(
        self, wav_path: Path, language: str, assess_pronunciation: bool = False
    ) -> RecognitionResult:
        locale = _LOCALES.get(language, language)

        def attempt(resource: SpeechResource) -> list[Any]:
            config = speech_config(self._credential, resource)
            config.speech_recognition_language = locale
            config.output_format = speechsdk.OutputFormat.Detailed
            config.request_word_level_timestamps()
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=config,
                audio_config=speechsdk.audio.AudioConfig(filename=str(wav_path)),
            )
            if assess_pronunciation:
                _assessment_config(locale).apply_to(recognizer)
            return _run_continuous(recognizer, timeout_sec=_timeout(wav_path))

        segments = self._failover.run(attempt)
        return RecognitionResult(
            verbatim=_verbatim(segments),
            pronunciation=_pronunciation(segments) if assess_pronunciation else None,
        )


class AzureSpeechSynthesizer:
    """Versión mejorada a mp3 con voz neural (RF-16). Las voces son configuración."""

    def __init__(
        self,
        credential: TokenCredential,
        resources: Sequence[SpeechResource],
        voices: Mapping[VoiceGender, str],
    ) -> None:
        self._credential = credential
        self._failover = _Failover(resources)
        self._voices = dict(voices)

    def synthesize(self, text: str, language: str, voice: VoiceGender) -> bytes:
        # Las dos voces configuradas son de inglés de EE. UU., el único idioma practicado.
        def attempt(resource: SpeechResource) -> bytes:
            config = speech_config(self._credential, resource)
            config.speech_synthesis_voice_name = self._voices[voice]
            config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
            )
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)
            result = synthesizer.speak_text_async(text).get()
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                return bytes(result.audio_data)
            details = result.cancellation_details
            code, message = str(details.error_code), details.error_details or ""
            if "TooManyRequests" in code or "quota" in message.lower():
                raise ServiceQuotaError(
                    "La voz sintética no está disponible en este momento. Intenta más tarde."
                )
            raise RuntimeError(f"Speech no sintetizó el audio: {code}: {message}")

        return self._failover.run(attempt)


def _assessment_config(locale: str) -> speechsdk.PronunciationAssessmentConfig:
    """Modo no guionizado (sin texto de referencia), por fonema y en IPA (ADR 0003)."""
    config = speechsdk.PronunciationAssessmentConfig(
        reference_text="",
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
        enable_miscue=False,
    )
    config.phoneme_alphabet = "IPA"
    if locale in _PROSODY_LOCALES:
        config.enable_prosody_assessment()
    return config


def _best(segment: Any) -> Any:
    return (segment.get("NBest") or [{}])[0]


def _verbatim(segments: list[Any]) -> VerbatimTranscript:
    words: list[TimedWord] = []
    lexical: list[str] = []
    for segment in segments:
        best = _best(segment)
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
    return VerbatimTranscript(lexical=" ".join(lexical), words=words)


def _pronunciation(segments: list[Any]) -> PronunciationAssessment | None:
    """Puntajes globales ponderados por palabras de cada segmento y palabras con problema.

    `word_index` es la posición de la palabra en `VerbatimTranscript.words`, que sale de los
    mismos segmentos en el mismo orden.
    """
    totals = dict.fromkeys(_SCORES, 0.0)
    weights = dict.fromkeys(_SCORES, 0)
    issues: list[PronunciationIssue] = []
    index = 0
    for segment in segments:
        best = _best(segment)
        words = best.get("Words", [])
        scores = best.get("PronunciationAssessment", {})
        for key, source in _SCORES.items():
            if source in scores:
                totals[key] += scores[source] * len(words)
                weights[key] += len(words)
        for w in words:
            assessment = w.get("PronunciationAssessment", {})
            error = assessment.get("ErrorType", "None")
            score = float(assessment.get("AccuracyScore", 100.0))
            if error == "Mispronunciation" or score < _LOW_SCORE:
                issues.append(
                    PronunciationIssue(
                        word=w["Word"],
                        score=score,
                        error_type=error if error != "None" else "LowAccuracy",
                        weak_phonemes=[
                            p["Phoneme"]
                            for p in w.get("Phonemes", [])
                            if p.get("Phoneme")
                            and p.get("PronunciationAssessment", {}).get("AccuracyScore", 100.0)
                            < _LOW_SCORE
                        ],
                        word_index=index,
                    )
                )
            index += 1
    averages = {k: round(totals[k] / weights[k], 1) for k in _SCORES if weights[k]}
    if "pron_score" not in averages:
        return None
    return PronunciationAssessment(
        pron_score=averages["pron_score"],
        accuracy=averages.get("accuracy", 0.0),
        fluency=averages.get("fluency", 0.0),
        prosody=averages.get("prosody"),
        issues=issues,
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
        # F0 rechaza solicitudes al agotar sus 5 horas del mes o por concurrencia.
        if "TooManyRequests" in code or "quota" in details.lower():
            raise ServiceQuotaError(
                "El reconocimiento de voz no tiene capacidad disponible en este momento. "
                "Si se repite, avísale al admin."
            )
        raise RuntimeError(f"Speech canceló el reconocimiento: {code}: {details}")
    return segments
