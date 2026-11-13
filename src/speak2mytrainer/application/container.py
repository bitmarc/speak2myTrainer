"""El conjunto de puertos que usan los adaptadores de entrada. `bootstrap` decide qué hay detrás."""

from __future__ import annotations

from dataclasses import dataclass, field

from speak2mytrainer.application.ports import (
    AudioConverter,
    AudioStorage,
    JobQueue,
    NullTelemetry,
    PracticeRepository,
    SpeechRecognizer,
    SpeechSynthesizer,
    Telemetry,
    TextAnalyzer,
    Transcriber,
    UserDirectory,
)
from speak2mytrainer.application.use_cases.process_attempt import ProcessAttempt
from speak2mytrainer.application.use_cases.submit_attempt import SubmitAttempt
from speak2mytrainer.domain.cost import Prices


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
    prices: Prices = field(default_factory=Prices)
    telemetry: Telemetry = field(default_factory=NullTelemetry)

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
            self.prices,
            self.telemetry,
        )
