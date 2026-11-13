"""Puertos: lo que el núcleo necesita del mundo exterior, nombrado por capacidad.

Cada puerto tiene un adaptador de Azure en `adapters/outbound/` y un fake en
`adapters/outbound/fakes/`. Los tipos de los SDK nunca cruzan esta frontera.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from speak2mytrainer.domain.models import (
    Attempt,
    Practice,
    PronunciationAssessment,
    TextAnalysis,
    UserProfile,
    VerbatimTranscript,
    VoiceGender,
)


@dataclass(frozen=True)
class Transcript:
    text: str
    model: str


@dataclass(frozen=True)
class RecognitionResult:
    verbatim: VerbatimTranscript
    pronunciation: PronunciationAssessment | None = None
    paid: bool = False  # la atendió un recurso de pago (S0), para el costo estimado


@dataclass(frozen=True)
class AnalysisResult:
    analysis: TextAnalysis
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Synthesis:
    audio: bytes  # mp3
    paid: bool = False


@dataclass(frozen=True)
class AnalysisRequest:
    """`transcript` es el texto de registro; `verbatim` y `candidates` son la evidencia de
    disfluencias de Speech y de la alineación (ADR 0002)."""

    transcript: str
    context: str | None
    feedback_language: str
    practice_language: str
    verbatim: str | None = None
    candidates: tuple[str, ...] = ()
    previous_transcript: str | None = None
    previous_analysis: TextAnalysis | None = None


@dataclass(frozen=True)
class AttemptJob:
    user_id: str
    practice_id: str
    attempt_id: str


class Transcriber(Protocol):
    """Audio (WAV 16 kHz mono) al texto de registro: legible, el que ve el usuario (ADR 0002)."""

    def transcribe(self, wav_path: Path, language: str) -> Transcript: ...


class SpeechRecognizer(Protocol):
    """Audio a forma léxica con marcas de tiempo por palabra (ADR 0002).

    Con `assess_pronunciation` devuelve también los puntajes de pronunciación en modo no
    guionizado (ADR 0003). Esa forma léxica pierde hesitaciones: para las muletillas se usa
    siempre una pasada sin evaluación.
    """

    def recognize(
        self, wav_path: Path, language: str, assess_pronunciation: bool = False
    ) -> RecognitionResult: ...


class AudioConverter(Protocol):
    """Inspección y conversión de audio (ffmpeg). `suffix` es la extensión original, con punto."""

    def duration_sec(self, data: bytes, suffix: str) -> float: ...

    def to_wav16k(self, data: bytes, suffix: str, dst: Path) -> None: ...

    def to_m4a(self, data: bytes, suffix: str) -> bytes:
        """AAC mono comprimido para guardar el audio después del análisis."""
        ...


class TextAnalyzer(Protocol):
    """Transcripción, contexto e intento previo a análisis estructurado."""

    @property
    def model(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    def analyze(self, request: AnalysisRequest) -> AnalysisResult: ...


class SpeechSynthesizer(Protocol):
    """Texto a audio mp3 con voz neural, en el idioma practicado."""

    def synthesize(self, text: str, language: str, voice: VoiceGender) -> Synthesis: ...


class AudioStorage(Protocol):
    def save(self, path: str, data: bytes, content_type: str) -> None: ...

    def read(self, path: str) -> bytes: ...

    def signed_url(self, path: str, ttl: timedelta) -> str: ...

    def delete(self, path: str) -> None: ...

    def delete_prefix(self, prefix: str) -> None: ...


class PracticeRepository(Protocol):
    def add_practice(self, practice: Practice) -> None: ...

    def get_practice(self, user_id: str, practice_id: str) -> Practice | None: ...

    def list_practices(self, user_id: str) -> list[Practice]: ...

    def update_practice(self, practice: Practice) -> None: ...

    def delete_practice(self, user_id: str, practice_id: str) -> None: ...

    def add_attempt(self, attempt: Attempt) -> None: ...

    def get_attempt(self, user_id: str, attempt_id: str) -> Attempt | None: ...

    def list_attempts(self, user_id: str, practice_id: str) -> list[Attempt]: ...

    def update_attempt(self, attempt: Attempt) -> None: ...

    def delete_all(self, user_id: str) -> None: ...


class UserDirectory(Protocol):
    """Lista blanca, preferencias y cuotas."""

    def get(self, user_id: str) -> UserProfile | None: ...

    def save(self, user: UserProfile) -> None: ...

    def list_users(self) -> list[UserProfile]: ...


class JobQueue(Protocol):
    def enqueue(self, job: AttemptJob) -> None: ...


# Valores que admite un atributo de traza (los mismos que OpenTelemetry).
Attribute = str | int | float | bool


class Telemetry(Protocol):
    """Trazas por intento: cuánto tarda cada paso y cuánto cuesta (ADR 0005).

    Los atributos nunca llevan datos personales (correo, texto del usuario): solo ids,
    duraciones, conteos y costos.
    """

    def span(self, name: str, **attributes: Attribute) -> AbstractContextManager[None]: ...

    def annotate(self, **attributes: Attribute) -> None:
        """Agrega atributos al tramo activo."""
        ...


class NullTelemetry:
    """Sin telemetría: la usan los tests y el modo local."""

    @contextmanager
    def span(self, name: str, **attributes: Attribute) -> Iterator[None]:
        yield

    def annotate(self, **attributes: Attribute) -> None:
        pass
