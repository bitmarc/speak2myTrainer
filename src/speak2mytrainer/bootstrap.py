"""Raíz de composición: el único módulo que conoce los adaptadores concretos."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from speak2mytrainer.adapters.outbound import fakes
from speak2mytrainer.application.container import Container
from speak2mytrainer.domain.cost import Prices

__all__ = ["AzureSettings", "Container", "Environment", "Settings", "build_container"]


class Environment(StrEnum):
    LOCAL = "local"
    CI = "ci"
    AZURE = "azure"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="S2MT_", env_file=".env", extra="ignore")

    env: Environment = Environment.LOCAL
    local_data_dir: Path = Path(".data")
    admin_email: str | None = None
    # Usuario de la sesión cuando no hay Easy Auth delante (desarrollo local).
    dev_user: str | None = None


class AzureSettings(BaseSettings):
    """Endpoints y deployments: los escribe `scripts/deploy-infra.ps1` en `.env` y Bicep en las
    variables de los contenedores. Nunca hay llaves."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_endpoint: str
    azure_openai_transcribe_deployment: str
    azure_openai_llm_deployment: str
    azure_openai_api_version: str = "2025-03-01-preview"
    azure_speech_resource_id: str
    azure_speech_region: str
    # Recurso S0 de respaldo (Fase 2): solo se usa cuando F0 rechaza por cuota o concurrencia.
    azure_speech_fallback_resource_id: str | None = None
    azure_speech_fallback_region: str | None = None
    azure_tts_voice_female: str = "en-US-AvaNeural"
    azure_tts_voice_male: str = "en-US-AndrewNeural"
    azure_cosmos_endpoint: str
    azure_cosmos_database: str
    azure_storage_blob_endpoint: str
    azure_storage_queue_endpoint: str
    # Precios para el costo estimado de cada intento (USD). Si cambia el modelo o la región,
    # se cambian estas variables, no el código. Valores del PRD (East US 2, 13-nov-2026).
    # Application Insights (ADR 0005). Sin ella no se exporta telemetría.
    applicationinsights_connection_string: str | None = None
    price_llm_input_per_million: float = 0.40
    price_llm_output_per_million: float = 1.60
    price_transcribe_per_minute: float = 0.003
    price_speech_per_hour: float = 1.0
    price_tts_per_million_chars: float = 15.0

    def prices(self) -> Prices:
        return Prices(
            llm_input_per_million=self.price_llm_input_per_million,
            llm_output_per_million=self.price_llm_output_per_million,
            transcribe_per_minute=self.price_transcribe_per_minute,
            speech_per_hour=self.price_speech_per_hour,
            tts_per_million_chars=self.price_tts_per_million_chars,
        )


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or Settings()
    match settings.env:
        case Environment.LOCAL | Environment.CI:
            return Container(
                transcriber=fakes.FakeTranscriber(),
                recognizer=fakes.FakeSpeechRecognizer(issues=fakes.demo_issues()),
                converter=fakes.FakeAudioConverter(),
                analyzer=fakes.FakeTextAnalyzer(fakes.demo_analysis()),
                synthesizer=fakes.FakeSpeechSynthesizer(),
                audio=fakes.LocalFolderAudioStorage(settings.local_data_dir),
                practices=fakes.InMemoryPracticeRepository(),
                users=fakes.InMemoryUserDirectory(),
                queue=fakes.InMemoryJobQueue(),
                admin_email=settings.admin_email,
            )
        case Environment.AZURE:
            return _azure_container(settings, AzureSettings())


def _azure_container(settings: Settings, azure: AzureSettings) -> Container:
    # Imports diferidos: en local y en CI no hace falta cargar los SDK de Azure.
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    from speak2mytrainer.adapters.outbound.app_insights import OpenTelemetryTelemetry
    from speak2mytrainer.adapters.outbound.azure_openai.analyzer import AzureOpenAITextAnalyzer
    from speak2mytrainer.adapters.outbound.azure_openai.transcriber import AzureOpenAITranscriber
    from speak2mytrainer.adapters.outbound.azure_speech import (
        AzureSpeechRecognizer,
        AzureSpeechSynthesizer,
        SpeechResource,
    )
    from speak2mytrainer.adapters.outbound.blob import BlobAudioStorage
    from speak2mytrainer.adapters.outbound.cosmos import (
        CosmosPracticeRepository,
        CosmosStore,
        CosmosUserDirectory,
    )
    from speak2mytrainer.adapters.outbound.ffmpeg import FfmpegAudioConverter
    from speak2mytrainer.adapters.outbound.storage_queue import StorageQueueJobQueue, queue_client
    from speak2mytrainer.domain.models import VoiceGender

    # En Container Apps toma la identidad administrada (AZURE_CLIENT_ID); en local, `az login`.
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )
    speech = [SpeechResource(azure.azure_speech_resource_id, azure.azure_speech_region)]
    if azure.azure_speech_fallback_resource_id:
        speech.append(
            SpeechResource(
                azure.azure_speech_fallback_resource_id,
                azure.azure_speech_fallback_region or azure.azure_speech_region,
                paid=True,
            )
        )
    cosmos = CosmosStore(azure.azure_cosmos_endpoint, azure.azure_cosmos_database, credential)
    return Container(
        transcriber=AzureOpenAITranscriber(
            azure.azure_openai_endpoint,
            azure.azure_openai_transcribe_deployment,
            token_provider,
            azure.azure_openai_api_version,
        ),
        recognizer=AzureSpeechRecognizer(credential, speech),
        converter=FfmpegAudioConverter(),
        analyzer=AzureOpenAITextAnalyzer(
            azure.azure_openai_endpoint,
            azure.azure_openai_llm_deployment,
            token_provider,
            azure.azure_openai_api_version,
        ),
        synthesizer=AzureSpeechSynthesizer(
            credential,
            speech,
            {
                VoiceGender.FEMALE: azure.azure_tts_voice_female,
                VoiceGender.MALE: azure.azure_tts_voice_male,
            },
        ),
        audio=BlobAudioStorage(azure.azure_storage_blob_endpoint, credential),
        practices=CosmosPracticeRepository(cosmos),
        users=CosmosUserDirectory(cosmos),
        queue=StorageQueueJobQueue(queue_client(azure.azure_storage_queue_endpoint, credential)),
        admin_email=settings.admin_email,
        prices=azure.prices(),
        telemetry=OpenTelemetryTelemetry(),
    )
