"""El conjunto de puertos que usan los adaptadores de entrada. `bootstrap` decide qué hay detrás."""

from __future__ import annotations

from dataclasses import dataclass

from speak2mytrainer.application.ports import (
    AudioConverter,
    AudioStorage,
    JobQueue,
    PracticeRepository,
    SpeechRecognizer,
    SpeechSynthesizer,
    TextAnalyzer,
    Transcriber,
    UserDirectory,
)
from speak2mytrainer.application.use_cases.process_attempt import ProcessAttempt
from speak2mytrainer.application.use_cases.submit_attempt import SubmitAttempt


@dataclass(frozen=True)
class Container:
    transcriber: Transcriber
    recognizer: SpeechRecognizer
    converter: AudioConverter
    analyzer: TextAnalyzer
    synthesizer: SpeechSynthesizer
    audio: AudioStorage
    practices: PracticeRepository
    users: UserDirectory
    queue: JobQueue
    admin_email: str | None = None

    @property
    def submit_attempt(self) -> SubmitAttempt:
        return SubmitAttempt(self.practices, self.users, self.audio, self.queue, self.converter)

    @property
    def process_attempt(self) -> ProcessAttempt:
        return ProcessAttempt(
            self.practices,
            self.users,
            self.audio,
            self.converter,
            self.transcriber,
            self.recognizer,
            self.analyzer,
        )
