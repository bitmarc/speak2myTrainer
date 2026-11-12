"""Adaptadores falsos para tests y desarrollo local sin Azure."""

from __future__ import annotations

from collections import deque
from datetime import timedelta
from pathlib import Path

from speak2mytrainer.application.ports import AnalysisRequest, AttemptJob, Transcript
from speak2mytrainer.domain.models import (
    Attempt,
    Practice,
    PronunciationAssessment,
    TextAnalysis,
    UserProfile,
)


class FakeTranscriber:
    def __init__(self, text: str = "well um I once worked on a project") -> None:
        self.text = text

    def transcribe(self, wav_path: Path, language: str) -> Transcript:
        return Transcript(text=self.text, model="fake-transcriber")


class FakePronunciationAssessor:
    def __init__(self, assessment: PronunciationAssessment | None = None) -> None:
        self.assessment = assessment or PronunciationAssessment(
            pron_score=80.0, accuracy=82.0, fluency=78.0, prosody=75.0
        )

    def assess(
        self, wav_path: Path, language: str, reference_text: str | None = None
    ) -> PronunciationAssessment:
        return self.assessment


class FakeTextAnalyzer:
    model = "fake-llm"
    prompt_version = "fake"

    def __init__(self, analysis: TextAnalysis | None = None) -> None:
        self.analysis = analysis or TextAnalysis(improved_version="", next_steps=[])
        self.requests: list[AnalysisRequest] = []

    def analyze(self, request: AnalysisRequest) -> TextAnalysis:
        self.requests.append(request)
        return self.analysis


class FakeSpeechSynthesizer:
    def synthesize(self, text: str, language: str) -> bytes:
        return b""


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
