"""Spike: ¿qué motor conserva las muletillas?

Corre cada audio de spikes/audio/ por:
  1. gpt-4o-mini-transcribe sin prompt
  2. gpt-4o-mini-transcribe con prompt de estilo verbatim
  3. Azure AI Speech STT (reconocimiento continuo, forma léxica y forma display)
  4. Opcionales, si existe su deployment: whisper y gpt-transcribe, con y sin el prompt verbatim

Genera spikes/results/transcribe_report.md con conteos de muletillas, repeticiones y latencia,
y un JSON por audio con las transcripciones completas. Con --engines solo corre esos motores y
reutiliza del JSON previo los resultados de los demás.

Uso:  uv run --all-extras python spikes/spike_transcribe.py [--only nombre_audio]
                                                             [--engines whisper,gpt-transcribe]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    COGNITIVE_SCOPE,
    RESULTS_DIR,
    count_fillers,
    credential,
    duration_sec,
    env,
    list_audios,
    normalize,
    run_continuous,
    save_json,
    speech_config,
)

# El prompt de gpt-4o-*-transcribe funciona como ejemplo de estilo: un texto con muletillas
# induce al modelo a conservarlas.
VERBATIM_PROMPT = (
    "Transcribe verbatim, exactly as spoken, including filler words and disfluencies. "
    "Umm, so, uh, I was, like, thinking that we- we could, eh, build the the system... "
    "Hmm, I mean, erm, it was, you know, kind of hard."
)


def openai_client():  # type: ignore[no-untyped-def]
    from azure.identity import get_bearer_token_provider
    from openai import AzureOpenAI

    return AzureOpenAI(
        azure_endpoint=env("AZURE_OPENAI_ENDPOINT"),
        azure_ad_token_provider=get_bearer_token_provider(credential(), COGNITIVE_SCOPE),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-03-01-preview"),
    )


def transcribe_openai(wav: Path, prompt: str | None, deployment: str | None = None) -> str:
    client = openai_client()
    with wav.open("rb") as f:
        kwargs: dict[str, object] = {
            "model": deployment or env("AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT"),
            "file": f,
            "language": "en",
            "temperature": 0,
            "response_format": "json",
        }
        if prompt:
            kwargs["prompt"] = prompt
        result = client.audio.transcriptions.create(**kwargs)  # type: ignore[call-overload]
    return str(result.text)


def transcribe_speech(wav: Path) -> dict[str, str]:
    import azure.cognitiveservices.speech as speechsdk

    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config(),
        audio_config=speechsdk.audio.AudioConfig(filename=str(wav)),
    )
    segments = run_continuous(recognizer)
    lexical = " ".join(s["NBest"][0]["Lexical"] for s in segments if s.get("NBest"))
    display = " ".join(s.get("DisplayText", "") for s in segments)
    return {"lexical": lexical, "display": display}


def timed[T](fn: Callable[..., T], *args: object) -> tuple[T, float]:
    start = time.perf_counter()
    result = fn(*args)
    return result, round(time.perf_counter() - start, 1)


# Motor base → función que devuelve {nombre en el reporte: texto}. Los deployments extra son
# nombres fijos porque solo existen para este spike.
def run_mini(wav: Path) -> dict[str, str]:
    return {
        "gpt-4o-mini-transcribe": transcribe_openai(wav, None),
        "gpt-4o-mini-transcribe + verbatim": transcribe_openai(wav, VERBATIM_PROMPT),
    }


def run_speech(wav: Path) -> dict[str, str]:
    speech = transcribe_speech(wav)
    return {"Speech STT (léxico)": speech["lexical"], "Speech STT (display)": speech["display"]}


def run_deployment(deployment: str) -> Callable[[Path], dict[str, str]]:
    def run(wav: Path) -> dict[str, str]:
        return {
            deployment: transcribe_openai(wav, None, deployment),
            f"{deployment} + verbatim": transcribe_openai(wav, VERBATIM_PROMPT, deployment),
        }

    return run


ENGINES: dict[str, Callable[[Path], dict[str, str]]] = {
    "mini": run_mini,
    "speech": run_speech,
    "whisper": run_deployment("whisper"),
    "gpt-transcribe": run_deployment("gpt-transcribe"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Procesar solo el audio cuyo nombre contiene este texto")
    parser.add_argument(
        "--engines",
        default="mini,speech",
        help=f"Motores a correr, separados por coma: {', '.join(ENGINES)}",
    )
    args = parser.parse_args()
    selected = args.engines.split(",")

    audios = [a for a in list_audios() if not args.only or args.only in a.name]
    rows: list[str] = []
    details: list[str] = []

    for audio in audios:
        wav = normalize(audio)
        seconds = duration_sec(wav)
        print(f"→ {audio.name} ({seconds:.0f} s)")

        # Resultados previos de los motores que no se corren esta vez.
        previous_file = RESULTS_DIR / f"{audio.stem}.transcribe.json"
        previous = (
            json.loads(previous_file.read_text(encoding="utf-8")) if previous_file.exists() else {}
        )
        engines: dict[str, tuple[str, float]] = {
            name: (value["text"], value["latency_sec"])
            for name, value in previous.items()
            if isinstance(value, dict)
        }
        for key in selected:
            texts, latency = timed(ENGINES[key], wav)
            # La latencia es la de la llamada completa del motor (dos pasadas en los de OpenAI).
            engines |= {name: (text, latency) for name, text in texts.items()}

        save_json(
            f"{audio.stem}.transcribe.json",
            {"audio": audio.name, "duration_sec": seconds}
            | {name: {"text": text, "latency_sec": t} for name, (text, t) in engines.items()},
        )

        details.append(f"\n## {audio.name} ({seconds:.0f} s)\n")
        for name, (text, latency) in engines.items():
            c = count_fillers(text)
            per_min = c.hesitations / (seconds / 60)
            rows.append(
                f"| {audio.name} | {name} | {c.words} | {c.hesitations} ({per_min:.1f}/min) | "
                f"{c.repetitions} | {', '.join(c.examples) or '—'} | {latency} s |"
            )
            details.append(f"**{name}**\n\n> {text}\n")

    report = [
        "# Spike de transcripción verbatim\n",
        "Conteo automático por regex. Revisar a mano contra el audio: manda lo que se oye.\n",
        "| Audio | Motor | Palabras | Muletillas de pausa | Repeticiones | Formas | Latencia |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *rows,
        "\n# Transcripciones\n",
        *details,
    ]
    out = RESULTS_DIR / "transcribe_report.md"
    out.write_text("\n".join(report), encoding="utf-8")
    print(f"Reporte: {out}")


if __name__ == "__main__":
    main()
