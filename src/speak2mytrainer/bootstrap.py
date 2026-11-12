"""Raíz de composición: el único módulo que conoce los adaptadores concretos."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from speak2mytrainer.adapters.outbound import fakes
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


class Environment(StrEnum):
    LOCAL = "local"
    CI = "ci"
    AZURE = "azure"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="S2MT_", env_file=".env", extra="ignore")

    env: Environment = Environment.LOCAL
    local_data_dir: Path = Path(".data")
    admin_email: str | None = None


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


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or Settings()
    match settings.env:
        case Environment.LOCAL | Environment.CI:
            return Container(
                transcriber=fakes.FakeTranscriber(),
                recognizer=fakes.FakeSpeechRecognizer(),
                converter=fakes.FakeAudioConverter(),
                analyzer=fakes.FakeTextAnalyzer(),
                synthesizer=fakes.FakeSpeechSynthesizer(),
                audio=fakes.LocalFolderAudioStorage(settings.local_data_dir),
                practices=fakes.InMemoryPracticeRepository(),
                users=fakes.InMemoryUserDirectory(),
                queue=fakes.InMemoryJobQueue(),
            )
        case Environment.AZURE:
            # Los adaptadores de Azure llegan en la Fase 1.
            raise NotImplementedError("Adaptadores de Azure pendientes (Fase 1)")
