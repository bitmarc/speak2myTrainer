"""Ejecuta el set de evaluación contra el TextAnalyzer real de Azure OpenAI.

Mide falsos positivos y recall en muletillas y en errores gramaticales (severity = error).
Meta del PRD: 0 falsos positivos y recall ≥ 90%.

Cada caso reproduce el pipeline del job (ADR 0002): `text` es el texto de registro y
`verbatim` (opcional, por defecto el mismo texto) la forma léxica de Speech; los candidatos
salen de alinear ambos y las hesitaciones las cuenta Python.

Los casos con `split: test` (fragmentos reales) no se usan para ajustar el prompt: se reportan
aparte para detectar sobreajuste.

El LLM varía entre corridas aunque la temperatura sea 0. Con `--runs N` cada caso se evalúa N
veces: la meta exige 0 falsos positivos en TODAS las corridas, recall promedio ≥ 90% y que la
comparación (casos con `previous`) acierte siempre.

Uso:  uv run --all-extras python evals/run_eval.py [--strict] [--runs N] [--only id]
                                                   [--split dev|test] [--prompt v1|v2]
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
from speak2mytrainer.domain.disfluency import combine_fillers, disfluency_candidates
from speak2mytrainer.domain.models import GrammarIssue, Severity, TextAnalysis

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


def previous_attempt(case: dict[str, Any]) -> tuple[str | None, TextAnalysis | None]:
    previous = case.get("previous")
    if not previous:
        return None, None
    grammar = [
        GrammarIssue(quote=g["quote"], fix=g["fix"], why=g.get("why", ""), severity=g["severity"])
        for g in previous.get("grammar", [])
    ]
    return previous["text"], TextAnalysis(grammar=grammar, improved_version="")


def score_comparison(case: dict[str, Any], analysis: TextAnalysis, failures: list[str]) -> None:
    """Solo booleanos: si `fixed` y `regressed` traen algo cuando deben (el texto es libre)."""
    if "previous" not in case:
        return
    comparison = analysis.comparison
    if comparison is None:
        failures.append(f"{case['id']}: sin comparación")
        return
    for name in ("fixed", "regressed"):
        expected = case.get(f"expect_{name}", False)
        got = getattr(comparison, name)
        if bool(got) != expected:
            wanted = "algo" if expected else "nada"
            failures.append(f"{case['id']}: {name}={got} (se esperaba {wanted})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Exit 1 si no se cumple la meta")
    parser.add_argument("--only", help="Evaluar solo el caso con este id")
    parser.add_argument("--split", choices=["dev", "test"], help="Evaluar solo ese subconjunto")
    parser.add_argument("--runs", type=int, default=1, help="Corridas por caso (variación)")
    parser.add_argument("--prompt", default=PROMPT_VERSION, help="Versión del prompt")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    analyzer = AzureOpenAITextAnalyzer(
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        deployment=os.environ["AZURE_OPENAI_LLM_DEPLOYMENT"],
        token_provider=get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        ),
        prompt_version=args.prompt,
    )

    cases = yaml.safe_load(PHRASES.read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
    if args.split:
        cases = [c for c in cases if c.get("split", "dev") == args.split]

    # Una tupla (muletillas, errores) por split y por corrida.
    runs: list[dict[str, tuple[Score, Score]]] = []
    comparison_failures: list[str] = []
    raw: list[dict[str, Any]] = []
    for run in range(args.runs):
        scores = {split: (Score(), Score()) for split in ("dev", "test")}
        for case in cases:
            verbatim = case.get("verbatim", case["text"])
            previous_text, previous_analysis = previous_attempt(case)
            analysis = analyzer.analyze(
                AnalysisRequest(
                    transcript=case["text"],
                    context=case.get("context"),
                    feedback_language="es",
                    practice_language="en",
                    verbatim=verbatim,
                    candidates=tuple(disfluency_candidates(case["text"], verbatim)),
                    previous_transcript=previous_text,
                    previous_analysis=previous_analysis,
                )
            )
            analysis.fillers = combine_fillers(verbatim, analysis.fillers)
            fillers, errors = scores[case.get("split", "dev")]
            score_fillers(case, analysis, fillers)
            score_errors(case, analysis, errors)
            score_comparison(case, analysis, comparison_failures)
            raw.append({"id": case["id"], "run": run, "analysis": analysis.model_dump(mode="json")})
            print(".", end="", flush=True)
        runs.append(scores)
    print()

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{args.prompt}_{analyzer.model}.json"
    out.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"Prompt {args.prompt} · modelo {analyzer.model} · {len(cases)} casos · "
        f"{args.runs} corrida(s)"
    )
    evaluated = {c.get("split", "dev") for c in cases}
    passed = True
    for split in ("dev", "test"):
        if split not in evaluated:
            continue
        print(f"[{split}]")
        for i, name in enumerate(("Muletillas", "Errores")):
            per_run = [r[split][i] for r in runs]
            tp = sum(s.tp for s in per_run)
            total = sum(s.tp + s.fn for s in per_run)
            recall = tp / total if total else 1.0
            fps = [fp for s in per_run for fp in s.fp]
            worst = max(len(s.fp) for s in per_run)
            print(
                f"  {name:<11} recall {recall:6.1%}  ({tp}/{total})  FP {worst} en la peor corrida"
            )
            for fp in sorted(set(fps)):
                print(f"      FP {fp}")
            passed &= worst == 0 and recall >= 0.9
    if any("previous" in c for c in cases):
        print(f"  Comparación  {len(comparison_failures)} fallos")
        for failure in comparison_failures:
            print(f"      {failure}")
        passed &= not comparison_failures
    print(f"Detalle: {out}")

    print("META CUMPLIDA" if passed else "META NO CUMPLIDA")
    return 1 if args.strict and not passed else 0


if __name__ == "__main__":
    sys.exit(main())
