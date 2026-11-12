"""Ejecuta el set de evaluación contra el TextAnalyzer real de Azure OpenAI.

Mide falsos positivos y recall en muletillas y en errores gramaticales (severity = error).
Meta del PRD: 0 falsos positivos y recall ≥ 90%.

Uso:  uv run --all-extras python evals/run_eval.py [--strict] [--only id]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

from speak2mytrainer.adapters.outbound.azure_openai.analyzer import (
    PROMPT_VERSION,
    AzureOpenAITextAnalyzer,
)
from speak2mytrainer.application.ports import AnalysisRequest
from speak2mytrainer.domain.models import Severity, TextAnalysis

ROOT = Path(__file__).resolve().parent.parent
PHRASES = ROOT / "evals" / "phrases.yaml"
RESULTS = ROOT / "evals" / "results"


def norm(text: str) -> str:
    text = text.lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
    words = re.sub(r"[^\w' ]+", " ", text).split()
    # Un reinicio puede venir con el token repetido ("So, so"): cuenta como una ocurrencia.
    collapsed = [w for i, w in enumerate(words) if i == 0 or w != words[i - 1]]
    return " ".join(collapsed)


@dataclass
class Score:
    tp: int = 0
    fn: int = 0
    fp: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        total = self.tp + self.fn
        return self.tp / total if total else 1.0


def score_fillers(case: dict[str, Any], analysis: TextAnalysis, score: Score) -> None:
    expected = Counter(norm(t) for t in case.get("fillers", []))
    allowed = {norm(t) for t in case.get("allow_fillers", [])}
    for f in analysis.fillers:
        token = norm(f.token)
        if expected[token] > 0:
            expected[token] -= 1
            score.tp += 1
        elif token not in allowed:
            score.fp.append(f"{case['id']}: «{f.token}» en «{f.quote}»")
    score.fn += sum(expected.values())


def score_errors(case: dict[str, Any], analysis: TextAnalysis, score: Score) -> None:
    expected = [norm(e) for e in case.get("errors", [])]
    allowed = [norm(e) for e in case.get("allow_errors", [])]
    found: set[str] = set()
    for g in analysis.grammar:
        if g.severity is not Severity.ERROR:
            continue
        quote = norm(g.quote)
        match = next((e for e in expected if e in quote or quote in e), None)
        if match:
            found.add(match)
        elif not any(a in quote or quote in a for a in allowed):
            score.fp.append(f"{case['id']}: «{g.quote}» → «{g.fix}»")
    score.tp += len(found)
    score.fn += len(expected) - len(found)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Exit 1 si no se cumple la meta")
    parser.add_argument("--only", help="Evaluar solo el caso con este id")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    analyzer = AzureOpenAITextAnalyzer(
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        deployment=os.environ["AZURE_OPENAI_LLM_DEPLOYMENT"],
        token_provider=get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        ),
    )

    cases = yaml.safe_load(PHRASES.read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]

    fillers, errors = Score(), Score()
    raw: list[dict[str, Any]] = []
    for case in cases:
        analysis = analyzer.analyze(
            AnalysisRequest(
                transcript=case["text"],
                context=case.get("context"),
                feedback_language="es",
                practice_language="en",
            )
        )
        score_fillers(case, analysis, fillers)
        score_errors(case, analysis, errors)
        raw.append({"id": case["id"], "analysis": analysis.model_dump(mode="json")})
        print(".", end="", flush=True)
    print()

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{PROMPT_VERSION}_{analyzer.model}.json"
    out.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Prompt {PROMPT_VERSION} · modelo {analyzer.model} · {len(cases)} casos")
    for name, s in (("Muletillas", fillers), ("Errores", errors)):
        print(f"{name:<11} recall {s.recall:6.1%}  ({s.tp}/{s.tp + s.fn})  FP {len(s.fp)}")
        for fp in s.fp:
            print(f"    FP {fp}")
    print(f"Detalle: {out}")

    passed = all(not s.fp and s.recall >= 0.9 for s in (fillers, errors))
    print("META CUMPLIDA" if passed else "META NO CUMPLIDA")
    return 1 if args.strict and not passed else 0


if __name__ == "__main__":
    sys.exit(main())
