"""Entidades y objetos de valor del dominio. Sin E/S ni dependencias de infraestructura."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from speak2mytrainer.domain.errors import InvalidStatusTransitionError


def utcnow() -> datetime:
    return datetime.now(UTC)


class AttemptStatus(StrEnum):
    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    ASSESSING = "assessing"
    ANALYZING = "analyzing"
    DONE = "done"
    FAILED = "failed"


# `assessing` es opcional (solo si el intento pidió evaluar la pronunciación), por eso
# transcribing puede saltar directo a analyzing. Cualquier estado no terminal puede pasar a
# failed, y failed puede volver a queued para el reintento automático.
_TRANSITIONS: dict[AttemptStatus, frozenset[AttemptStatus]] = {
    AttemptStatus.QUEUED: frozenset({AttemptStatus.TRANSCRIBING}),
    AttemptStatus.TRANSCRIBING: frozenset({AttemptStatus.ASSESSING, AttemptStatus.ANALYZING}),
    AttemptStatus.ASSESSING: frozenset({AttemptStatus.ANALYZING}),
    AttemptStatus.ANALYZING: frozenset({AttemptStatus.DONE}),
    AttemptStatus.DONE: frozenset(),
    AttemptStatus.FAILED: frozenset({AttemptStatus.QUEUED}),
}


def can_transition(current: AttemptStatus, new: AttemptStatus) -> bool:
    if new is AttemptStatus.FAILED:
        return current not in (AttemptStatus.DONE, AttemptStatus.FAILED)
    return new in _TRANSITIONS[current]


class FillerType(StrEnum):
    HESITATION = "hesitation"  # pausa de duda: um, uh, eh
    RESTART = "restart"  # duda con reinicio: "to helps retrieve", "we build a eemm a system"
    LEXICAL = "lexical"  # muletilla léxica: like, you know, basically sin función gramatical


class Severity(StrEnum):
    ERROR = "error"
    SUGGESTION = "suggestion"
    STYLE = "style"


class Filler(BaseModel):
    quote: str
    token: str
    type: FillerType


class ValidNonFiller(BaseModel):
    quote: str
    token: str
    reason: str


class GrammarIssue(BaseModel):
    quote: str
    fix: str
    why: str
    severity: Severity


class PronunciationIssue(BaseModel):
    """Palabra con pronunciación débil según Speech (ADR 0003)."""

    word: str
    score: float  # precisión de la palabra, 0-100
    error_type: str  # Mispronunciation o LowAccuracy
    weak_phonemes: list[str] = Field(default_factory=list)  # IPA, los de puntaje bajo
    word_index: int | None = None  # posición en VerbatimTranscript.words, para alinear


class Comparison(BaseModel):
    """Contra el intento anterior de la misma práctica. Las listas las redacta el LLM; los
    conteos y el número del intento los pone Python."""

    fixed: list[str] = Field(default_factory=list)
    regressed: list[str] = Field(default_factory=list)
    adopted_suggestions: list[str] = Field(default_factory=list)
    fillers_before: int = 0
    fillers_after: int = 0
    previous_attempt_number: int | None = None


class TextAnalysis(BaseModel):
    """Lo que devuelve el analizador de texto, ya traducido a objetos de dominio."""

    fillers: list[Filler] = Field(default_factory=list)
    valid_non_fillers: list[ValidNonFiller] = Field(default_factory=list)
    grammar: list[GrammarIssue] = Field(default_factory=list)
    improved_version: str
    next_steps: list[str] = Field(default_factory=list)
    comparison: Comparison | None = None


class TimedWord(BaseModel):
    text: str
    start_sec: float
    end_sec: float


class VerbatimTranscript(BaseModel):
    """Forma léxica de Speech: conserva um/uh, repeticiones y reinicios (ADR 0002)."""

    lexical: str
    words: list[TimedWord] = Field(default_factory=list)

    def speaking_span_sec(self) -> float | None:
        """Tiempo entre la primera y la última palabra; None si no hay marcas de tiempo."""
        if not self.words:
            return None
        return max(self.words[-1].end_sec - self.words[0].start_sec, 0.0)


class PronunciationAssessment(BaseModel):
    pron_score: float
    accuracy: float
    fluency: float
    prosody: float | None = None  # solo existe para en-US
    issues: list[PronunciationIssue] = Field(default_factory=list)


class Metrics(BaseModel):
    duration_sec: float
    words: int
    wpm: float
    fillers_per_min: float
    restarts: int
    pron_score: float | None = None
    accuracy: float | None = None
    fluency: float | None = None
    prosody: float | None = None


class ModelInfo(BaseModel):
    transcribe: str
    llm: str
    prompt_version: str


class Practice(BaseModel):
    id: str
    user_id: str
    title: str
    context: str | None = None
    practice_language: str = "en"
    created_at: datetime = Field(default_factory=utcnow)
    attempt_count: int = 0
    last_attempt_at: datetime | None = None


class Attempt(BaseModel):
    id: str
    user_id: str
    practice_id: str
    number: int
    audio_blob: str
    duration_sec: float
    # Pronunciación opcional por intento: es una segunda pasada de Speech (ADR 0003).
    assess_pronunciation: bool = False
    status: AttemptStatus = AttemptStatus.QUEUED
    error: str | None = None
    transcript: str | None = None
    verbatim_transcript: str | None = None
    metrics: Metrics | None = None
    analysis: TextAnalysis | None = None
    pronunciation: PronunciationAssessment | None = None
    tts_blob: str | None = None
    models: ModelInfo | None = None
    cost_estimate_usd: float | None = None
    created_at: datetime = Field(default_factory=utcnow)

    def advance(self, new: AttemptStatus, error: str | None = None) -> None:
        if not can_transition(self.status, new):
            raise InvalidStatusTransitionError(self.status, new)
        self.status = new
        self.error = error if new is AttemptStatus.FAILED else None


class Quota(BaseModel):
    minutes_per_month: float = 60.0
    used_this_month: float = 0.0
    period_start: datetime = Field(default_factory=utcnow)

    def roll_over_if_needed(self, now: datetime) -> None:
        if (now.year, now.month) != (self.period_start.year, self.period_start.month):
            self.used_this_month = 0.0
            self.period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def remaining_minutes(self) -> float:
        return max(self.minutes_per_month - self.used_this_month, 0.0)

    def allows(self, duration_sec: float) -> bool:
        return duration_sec / 60 <= self.remaining_minutes()

    def consume(self, duration_sec: float) -> None:
        self.used_this_month += duration_sec / 60

    def refund(self, duration_sec: float) -> None:
        self.used_this_month = max(self.used_this_month - duration_sec / 60, 0.0)


class VoiceGender(StrEnum):
    """Voz con la que se escucha la versión mejorada (RF-16)."""

    FEMALE = "female"
    MALE = "male"


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


class UserProfile(BaseModel):
    id: str  # correo verificado por Google
    name: str
    role: Role = Role.USER
    allowed: bool = True
    feedback_language: str = "es"
    practice_language: str = "en"
    tts_voice: VoiceGender = VoiceGender.FEMALE
    quota: Quota = Field(default_factory=Quota)
