"""Esquema JSON que devuelve el LLM (Structured Outputs) y su traducción al dominio.

El núcleo nunca ve este JSON: `to_domain` lo valida contra las transcripciones y devuelve
objetos de dominio. Cualquier cita que no aparezca literalmente en su fuente se descarta,
porque una detección sin evidencia es un falso positivo en potencia (ADR 0002):

- muletillas y usos válidos, contra el texto de registro o la forma léxica de Speech;
- gramática, solo contra el texto de registro, para que un error de reconocimiento de Speech
  nunca se convierta en un error gramatical.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from speak2mytrainer.domain.models import (
    Comparison,
    Filler,
    FillerType,
    GrammarIssue,
    Severity,
    TextAnalysis,
    ValidNonFiller,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FillerOut(_Strict):
    quote: str
    token: str
    type: Literal["hesitation", "restart", "lexical"]


class ValidNonFillerOut(_Strict):
    quote: str
    token: str
    reason: str


class GrammarOut(_Strict):
    quote: str
    fix: str
    why: str
    severity: Literal["error", "suggestion", "style"]


class ComparisonOut(_Strict):
    fixed: list[str]
    regressed: list[str]
    adopted_suggestions: list[str]


class AnalysisOutput(_Strict):
    fillers: list[FillerOut]
    valid_non_fillers: list[ValidNonFillerOut]
    grammar: list[GrammarOut]
    improved_version: str
    next_steps: list[str]
    comparison: ComparisonOut | None

    def to_domain(
        self,
        transcript: str,
        verbatim: str | None = None,
        previous_filler_count: int | None = None,
    ) -> TextAnalysis:
        record = _normalize(transcript)
        speech = (record, _normalize(verbatim)) if verbatim else (record,)

        def grounded(
            quote: str, token: str | None = None, sources: tuple[str, ...] = speech
        ) -> bool:
            q = _normalize(quote)
            if not q.strip() or not any(q in source for source in sources):
                return False
            return token is None or _normalize(token) in q

        comparison = None
        if self.comparison is not None and previous_filler_count is not None:
            comparison = Comparison(
                fixed=self.comparison.fixed,
                regressed=self.comparison.regressed,
                adopted_suggestions=self.comparison.adopted_suggestions,
                fillers_before=previous_filler_count,
                fillers_after=0,  # se completa abajo con el conteo ya filtrado
            )

        # Si el modelo puso la misma ocurrencia en ambas listas, gana "uso válido": ante la duda,
        # no se cuenta como muletilla.
        valid_keys = {(_normalize(v.quote), _normalize(v.token)) for v in self.valid_non_fillers}
        fillers = [
            Filler(quote=f.quote, token=f.token, type=FillerType(f.type))
            for f in self.fillers
            if grounded(f.quote, f.token)
            and (_normalize(f.quote), _normalize(f.token)) not in valid_keys
        ]
        if comparison is not None:
            comparison.fillers_after = len(fillers)

        return TextAnalysis(
            fillers=fillers,
            valid_non_fillers=[
                ValidNonFiller(quote=v.quote, token=v.token, reason=v.reason)
                for v in self.valid_non_fillers
                if grounded(v.quote, v.token)
            ],
            grammar=[
                GrammarIssue(quote=g.quote, fix=g.fix, why=g.why, severity=Severity(g.severity))
                for g in self.grammar
                if grounded(g.quote, sources=(record,))
            ],
            improved_version=self.improved_version,
            next_steps=self.next_steps,
            comparison=comparison,
        )


_NON_WORD = re.compile(r"[^\w']+")


def _normalize(text: str) -> str:
    """Minúsculas y sin puntuación, para comparar citas sin depender de comas o comillas."""
    text = text.lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
    return " " + _NON_WORD.sub(" ", text).strip() + " "
