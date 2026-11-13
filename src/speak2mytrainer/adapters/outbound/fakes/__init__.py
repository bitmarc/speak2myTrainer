"""Adaptadores falsos para tests y desarrollo local sin Azure."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from speak2mytrainer.application.ports import (
    AnalysisRequest,
    AnalysisResult,
    AttemptJob,
    Attribute,
    RecognitionResult,
    Synthesis,
    Transcript,
)
from speak2mytrainer.domain.models import (
    Attempt,
    Comparison,
    Filler,
    FillerType,
    GrammarIssue,
    Practice,
    PronunciationAssessment,
    PronunciationIssue,
    Severity,
    TextAnalysis,
    TimedWord,
    UserProfile,
    VerbatimTranscript,
    VoiceGender,
)


class FakeTranscriber:
    def __init__(self, text: str = "well um I once worked on a project") -> None:
        self.text = text

    def transcribe(self, wav_path: Path, language: str) -> Transcript:
        return Transcript(text=self.text, model="fake-transcriber")


class FakeSpeechRecognizer:
    """Devuelve un texto léxico fijo con una palabra cada `seconds_per_word` segundos."""

    def __init__(
        self,
        lexical: str = "well um i once worked on a project",
        seconds_per_word: float = 0.4,
        issues: list[PronunciationIssue] | None = None,
        paid: bool = False,
    ) -> None:
        self.lexical = lexical
        self.seconds_per_word = seconds_per_word
        self.issues = issues or []
        self.paid = paid  # simula que respondió el recurso S0
        self.calls: list[bool] = []  # assess_pronunciation de cada llamada

    def recognize(
        self, wav_path: Path, language: str, assess_pronunciation: bool = False
    ) -> RecognitionResult:
        self.calls.append(assess_pronunciation)
        step = self.seconds_per_word
        words = [
            TimedWord(text=w, start_sec=i * step, end_sec=(i + 1) * step)
            for i, w in enumerate(self.lexical.split())
        ]
        pronunciation = (
            PronunciationAssessment(
                pron_score=80.0,
                accuracy=82.0,
                fluency=78.0,
                prosody=75.0,
                issues=[i.model_copy() for i in self.issues],
            )
            if assess_pronunciation
            else None
        )
        return RecognitionResult(
            verbatim=VerbatimTranscript(lexical=self.lexical, words=words),
            pronunciation=pronunciation,
            paid=self.paid,
        )


class FakeAudioConverter:
    """No convierte nada: informa una duración fija y copia los bytes al destino."""

    def __init__(self, duration: float = 30.0) -> None:
        self.duration = duration

    def duration_sec(self, data: bytes, suffix: str) -> float:
        return self.duration

    def to_wav16k(self, data: bytes, suffix: str, dst: Path) -> None:
        dst.write_bytes(data)

    def to_m4a(self, data: bytes, suffix: str) -> bytes:
        return b"m4a:" + data


def demo_analysis() -> TextAnalysis:
    """Un análisis con todos los bloques, para ver la interfaz en local sin Azure."""
    return TextAnalysis(
        fillers=[Filler(quote="well um I once", token="well", type=FillerType.LEXICAL)],
        grammar=[
            GrammarIssue(
                quote="worked on a project",
                fix="worked on a big project",
                why="Ejemplo local: el analizador real explica aquí la corrección.",
                severity=Severity.SUGGESTION,
            )
        ],
        improved_version="I once worked on a challenging project for a bank.",
        next_steps=["Haz pausas en silencio.", "Usa el pasado.", "Da un ejemplo concreto."],
        comparison=Comparison(fixed=["Ejemplo local de algo corregido"]),
    )


def demo_issues() -> list[PronunciationIssue]:
    """Una palabra a practicar sobre el texto léxico por defecto de `FakeSpeechRecognizer`."""
    return [
        PronunciationIssue(
            word="project",
            score=48,
            error_type="Mispronunciation",
            weak_phonemes=["dʒ"],
            word_index=7,
        )
    ]


class FakeTextAnalyzer:
    model = "fake-llm"
    prompt_version = "fake"
    # Uso fijo por análisis, para que el costo estimado sea predecible en los tests.
    input_tokens = 5_000
    output_tokens = 2_500

    def __init__(self, analysis: TextAnalysis | None = None) -> None:
        self.analysis = analysis or TextAnalysis(improved_version="", next_steps=[])
        self.requests: list[AnalysisRequest] = []

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        self.requests.append(request)
        return AnalysisResult(
            analysis=self.analysis.model_copy(deep=True),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


class FakeSpeechSynthesizer:
    """Devuelve bytes que identifican la voz y el texto; registra cada llamada."""

    def __init__(self, paid: bool = False) -> None:
        self.calls: list[tuple[str, str, VoiceGender]] = []
        self.paid = paid

    def synthesize(self, text: str, language: str, voice: VoiceGender) -> Synthesis:
        self.calls.append((text, language, voice))
        return Synthesis(audio=f"mp3:{voice}:{text}".encode(), paid=self.paid)


class LocalFolderAudioStorage:
    """Guarda audio en una carpeta local; la "URL firmada" es una ruta file://."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _resolve(self, path: str) -> Path:
        return self.root / path

    def save(self, path: str, data: bytes, content_type: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def read(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def signed_url(self, path: str, ttl: timedelta) -> str:
        return self._resolve(path).resolve().as_uri()

    def delete(self, path: str) -> None:
        self._resolve(path).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        if not self.root.exists():
            return
        for file in self.root.rglob("*"):
            if file.is_file() and file.relative_to(self.root).as_posix().startswith(prefix):
                file.unlink()


class InMemoryPracticeRepository:
    def __init__(self) -> None:
        self.practices: dict[str, Practice] = {}
        self.attempts: dict[str, Attempt] = {}

    def add_practice(self, practice: Practice) -> None:
        self.practices[practice.id] = practice.model_copy(deep=True)

    def get_practice(self, user_id: str, practice_id: str) -> Practice | None:
        p = self.practices.get(practice_id)
        return p.model_copy(deep=True) if p and p.user_id == user_id else None

    def list_practices(self, user_id: str) -> list[Practice]:
        found = [p for p in self.practices.values() if p.user_id == user_id]
        return sorted(found, key=lambda p: p.created_at, reverse=True)

    def update_practice(self, practice: Practice) -> None:
        self.practices[practice.id] = practice.model_copy(deep=True)

    def delete_practice(self, user_id: str, practice_id: str) -> None:
        if self.get_practice(user_id, practice_id):
            del self.practices[practice_id]
        self.attempts = {
            k: a
            for k, a in self.attempts.items()
            if not (a.user_id == user_id and a.practice_id == practice_id)
        }

    def add_attempt(self, attempt: Attempt) -> None:
        self.attempts[attempt.id] = attempt.model_copy(deep=True)

    def get_attempt(self, user_id: str, attempt_id: str) -> Attempt | None:
        a = self.attempts.get(attempt_id)
        return a.model_copy(deep=True) if a and a.user_id == user_id else None

    def list_attempts(self, user_id: str, practice_id: str) -> list[Attempt]:
        found = [
            a
            for a in self.attempts.values()
            if a.user_id == user_id and a.practice_id == practice_id
        ]
        return sorted(found, key=lambda a: a.number)

    def update_attempt(self, attempt: Attempt) -> None:
        self.attempts[attempt.id] = attempt.model_copy(deep=True)

    def delete_all(self, user_id: str) -> None:
        self.practices = {k: p for k, p in self.practices.items() if p.user_id != user_id}
        self.attempts = {k: a for k, a in self.attempts.items() if a.user_id != user_id}


class InMemoryUserDirectory:
    def __init__(self, users: list[UserProfile] | None = None) -> None:
        self.users = {u.id: u for u in users or []}

    def get(self, user_id: str) -> UserProfile | None:
        u = self.users.get(user_id)
        return u.model_copy(deep=True) if u else None

    def save(self, user: UserProfile) -> None:
        self.users[user.id] = user.model_copy(deep=True)

    def list_users(self) -> list[UserProfile]:
        return list(self.users.values())


class InMemoryJobQueue:
    def __init__(self) -> None:
        self.jobs: deque[AttemptJob] = deque()

    def enqueue(self, job: AttemptJob) -> None:
        self.jobs.append(job)


class RecordingTelemetry:
    """Registra los tramos abiertos y sus atributos, para verificar las trazas en los tests."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, Attribute]]] = []
        self._open: list[dict[str, Attribute]] = []

    @contextmanager
    def span(self, name: str, **attributes: Attribute) -> Iterator[None]:
        attrs = dict(attributes)
        self.spans.append((name, attrs))
        self._open.append(attrs)
        try:
            yield
        finally:
            self._open.pop()

    def annotate(self, **attributes: Attribute) -> None:
        if self._open:
            self._open[-1].update(attributes)
