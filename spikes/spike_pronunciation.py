"""Spike: evaluación de pronunciación no guionizada frente a guionizada.

- No guionizada: sin texto de referencia; Speech reconoce y evalúa a la vez.
- Guionizada: usa como referencia la transcripción verbatim del spike de transcripción
  (lo que Microsoft sugiere cuando el reconocimiento no guionizado es menos preciso).

Ambas con reconocimiento continuo y prosodia (solo en-US). Mide puntajes, palabras con
problemas, tiempo de reloj y minutos facturables (cada pasada se cobra como STT).

Uso:  uv run --extra azure python spikes/spike_pronunciation.py spikes/audio/mi_audio.m4a
      [--reference-engine "gpt-4o-mini-transcribe + verbatim"]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    RESULTS_DIR,
    duration_sec,
    normalize,
    run_continuous,
    save_json,
    speech_config,
)

LOW_ACCURACY = 60


def assess(wav: Path, reference_text: str) -> list[dict[str, Any]]:
    import azure.cognitiveservices.speech as speechsdk

    pa_config = speechsdk.PronunciationAssessmentConfig(
        reference_text=reference_text,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
        enable_miscue=bool(reference_text),
    )
    pa_config.enable_prosody_assessment()
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config(),
        audio_config=speechsdk.audio.AudioConfig(filename=str(wav)),
    )
    pa_config.apply_to(recognizer)
    return run_continuous(recognizer)


def summarize(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Promedio de los puntajes por segmento, ponderado por número de palabras."""
    keys = ["PronScore", "AccuracyScore", "FluencyScore", "ProsodyScore", "CompletenessScore"]
    totals = dict.fromkeys(keys, 0.0)
    weight = 0
    issues: list[dict[str, Any]] = []
    recognized: list[str] = []
    for seg in segments:
        best = seg["NBest"][0]
        words = best.get("Words", [])
        n = max(len(words), 1)
        weight += n
        for k in keys:
            totals[k] += best.get("PronunciationAssessment", {}).get(k, 0.0) * n
        recognized.append(best.get("Lexical", ""))
        for w in words:
            pa = w.get("PronunciationAssessment", {})
            error = pa.get("ErrorType", "None")
            if error != "None" or pa.get("AccuracyScore", 100) < LOW_ACCURACY:
                issues.append(
                    {"word": w["Word"], "accuracy": pa.get("AccuracyScore"), "error": error}
                )
    scores = {k: round(v / weight, 1) if weight else None for k, v in totals.items()}
    return {"scores": scores, "issues": issues, "recognized_text": " ".join(recognized)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--reference-engine", default="gpt-4o-mini-transcribe + verbatim")
    args = parser.parse_args()

    wav = normalize(args.audio)
    seconds = duration_sec(wav)
    transcripts = RESULTS_DIR / f"{args.audio.stem}.transcribe.json"
    if not transcripts.exists():
        raise SystemExit(f"Primero corre spike_transcribe.py (falta {transcripts.name})")
    reference = json.loads(transcripts.read_text(encoding="utf-8"))[args.reference_engine]["text"]

    results: dict[str, Any] = {}
    for mode, ref in (("no guionizada", ""), ("guionizada", reference)):
        start = time.perf_counter()
        segments = assess(wav, ref)
        elapsed = round(time.perf_counter() - start, 1)
        results[mode] = summarize(segments) | {"elapsed_sec": elapsed, "segments": len(segments)}
        print(f"{mode}: {results[mode]['scores']} en {elapsed} s")

    save_json(f"{args.audio.stem}.pronunciation.json", results)

    lines = [
        f"# Spike de pronunciación: {args.audio.name} ({seconds / 60:.1f} min)\n",
        f"Referencia para el modo guionizado: `{args.reference_engine}`.\n",
        "| Modo | Pron | Precisión | Fluidez | Prosodia | Completitud | Palabras con problema "
        "| Tiempo | Min. facturables |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for mode, r in results.items():
        s = r["scores"]
        lines.append(
            f"| {mode} | {s['PronScore']} | {s['AccuracyScore']} | {s['FluencyScore']} | "
            f"{s['ProsodyScore']} | {s['CompletenessScore']} | {len(r['issues'])} | "
            f"{r['elapsed_sec']} s | {seconds / 60:.1f} |"
        )
    for mode, r in results.items():
        lines.append(f"\n## {mode}: palabras con problema\n")
        lines += [f"- **{i['word']}**: {i['accuracy']} ({i['error']})" for i in r["issues"][:40]]
        lines.append(f"\nTexto reconocido:\n\n> {r['recognized_text']}\n")

    out = RESULTS_DIR / f"{args.audio.stem}.pronunciation_report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Reporte: {out}")


if __name__ == "__main__":
    main()
