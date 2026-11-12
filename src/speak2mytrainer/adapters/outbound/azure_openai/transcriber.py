"""Adaptador `Transcriber` con `gpt-4o-mini-transcribe`: el texto de registro (ADR 0002)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from openai import AzureOpenAI

from speak2mytrainer.application.ports import Transcript


class AzureOpenAITranscriber:
    def __init__(
        self,
        endpoint: str,
        deployment: str,
        token_provider: Callable[[], str],
        api_version: str = "2025-03-01-preview",
    ) -> None:
        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
        )
        self._deployment = deployment

    def transcribe(self, wav_path: Path, language: str) -> Transcript:
        # Sin prompt: en el spike, el prompt verbatim no cambió nada (ADR 0002).
        with wav_path.open("rb") as audio:
            result = self._client.audio.transcriptions.create(
                model=self._deployment,
                file=audio,
                language=language,
                temperature=0,
                response_format="json",
            )
        return Transcript(text=result.text.strip(), model=self._deployment)
