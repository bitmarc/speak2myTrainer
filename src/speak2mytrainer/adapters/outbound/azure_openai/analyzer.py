"""Adaptador `TextAnalyzer` sobre Azure OpenAI con Structured Outputs."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path

from openai import AzureOpenAI

from speak2mytrainer.adapters.outbound.azure_openai.schema import AnalysisOutput
from speak2mytrainer.application.ports import AnalysisRequest, AnalysisResult

PROMPT_VERSION = "v2"
_PROMPTS_DIR = Path(__file__).parent / "prompts"

_LANGUAGE_NAMES = {"es": "Spanish", "en": "English"}


@cache
def _system_prompt(version: str) -> str:
    return (_PROMPTS_DIR / f"analysis_{version}.md").read_text(encoding="utf-8")


class AzureOpenAITextAnalyzer:
    def __init__(
        self,
        endpoint: str,
        deployment: str,
        token_provider: Callable[[], str],
        api_version: str = "2025-03-01-preview",
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
        )
        self._deployment = deployment
        self._prompt_version = prompt_version

    @property
    def model(self) -> str:
        return self._deployment

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        language = _LANGUAGE_NAMES.get(request.feedback_language, request.feedback_language)
        system = _system_prompt(self._prompt_version).replace("{feedback_language}", language)

        payload: dict[str, object] = {
            "context": request.context or "(none)",
            "transcript": request.transcript,
        }
        if request.verbatim is not None:
            payload["verbatim"] = request.verbatim
            payload["disfluency_candidates"] = list(request.candidates)
        has_previous = request.previous_transcript is not None
        if request.previous_transcript is not None:
            payload["previous_attempt"] = {
                "transcript": request.previous_transcript,
                "feedback": (
                    request.previous_analysis.model_dump(mode="json")
                    if request.previous_analysis
                    else None
                ),
            }

        completion = self._client.chat.completions.parse(
            model=self._deployment,
            temperature=0,
            response_format=AnalysisOutput,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        message = completion.choices[0].message
        if message.parsed is None:
            raise RuntimeError(f"El modelo no devolvió un análisis válido: {message.refusal}")
        usage = completion.usage
        return AnalysisResult(
            analysis=message.parsed.to_domain(request.transcript, request.verbatim, has_previous),
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
