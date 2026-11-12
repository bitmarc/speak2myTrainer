"""Utilidades compartidas por los spikes de la Fase 0. Código desechable, fuera del paquete."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "spikes" / "audio"
RESULTS_DIR = ROOT / "spikes" / "results"
WAV_DIR = RESULTS_DIR / "wav"
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".ogg", ".webm", ".aac"}

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"

load_dotenv(ROOT / ".env")

# Muletillas de pausa: um, umm, uh, eh, erm, hmm, ah, em, eemm, mm...
HESITATION_RE = re.compile(r"\b(?:u+m+|u+h+m*|e+h+|e+r+m*|h+u*m+|a+h+|e+m+|m{2,})\b", re.IGNORECASE)
# Repeticiones inmediatas: "I I", "to to", "we- we".
REPETITION_RE = re.compile(r"\b(\w+)(?:-|,)?\s+\1\b", re.IGNORECASE)


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Falta la variable {name}. ¿Corriste scripts/deploy-infra.ps1?")
    return value


def tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    links = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
    winget_link = links / f"{name}.exe"
    if winget_link.exists():
        return str(winget_link)
    raise SystemExit(f"No se encontró {name}. Instálalo con: winget install Gyan.FFmpeg")


def list_audios() -> list[Path]:
    audios = sorted(p for p in AUDIO_DIR.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS)
    if not audios:
        raise SystemExit(f"No hay audios en {AUDIO_DIR}. Formatos: {sorted(AUDIO_EXTENSIONS)}")
    return audios


def normalize(src: Path) -> Path:
    """Convierte a WAV PCM 16 kHz mono, el formato que esperan Speech y el pipeline del job."""
    WAV_DIR.mkdir(parents=True, exist_ok=True)
    dst = WAV_DIR / f"{src.stem}.wav"
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(
            [tool("ffmpeg"), "-y", "-loglevel", "error", "-i", str(src),
             "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(dst)],
            check=True,
        )  # fmt: skip
    return dst


def duration_sec(path: Path) -> float:
    out = subprocess.run(
        [tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return float(out.stdout.strip())


@dataclass(frozen=True)
class FillerCount:
    hesitations: int
    repetitions: int
    words: int
    examples: list[str]


def count_fillers(text: str) -> FillerCount:
    hesitations = HESITATION_RE.findall(text)
    return FillerCount(
        hesitations=len(hesitations),
        repetitions=len(REPETITION_RE.findall(text)),
        words=len(re.findall(r"[A-Za-z']+", text)),
        examples=sorted({h.lower() for h in hesitations}),
    )


@cache
def credential() -> Any:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def speech_config() -> Any:
    """SpeechConfig con token de Entra: formato `aad#{resourceId}#{token}` (sin llaves)."""
    import azure.cognitiveservices.speech as speechsdk

    token = credential().get_token(COGNITIVE_SCOPE).token
    auth = f"aad#{env('AZURE_SPEECH_RESOURCE_ID')}#{token}"
    config = speechsdk.SpeechConfig(auth_token=auth, region=env("AZURE_SPEECH_REGION"))
    config.speech_recognition_language = "en-US"
    config.output_format = speechsdk.OutputFormat.Detailed
    config.request_word_level_timestamps()
    return config


def run_continuous(recognizer: Any) -> list[dict[str, Any]]:
    """Reconocimiento continuo (sin límite de 30 s). Devuelve el JSON de cada segmento."""
    import azure.cognitiveservices.speech as speechsdk

    done = threading.Event()
    segments: list[dict[str, Any]] = []
    errors: list[str] = []

    def on_recognized(evt: Any) -> None:
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            raw = evt.result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
            segments.append(json.loads(raw))

    def on_canceled(evt: Any) -> None:
        details = evt.cancellation_details
        if details.reason == speechsdk.CancellationReason.Error:
            errors.append(f"{details.error_code}: {details.error_details}")
        done.set()

    recognizer.recognized.connect(on_recognized)
    recognizer.canceled.connect(on_canceled)
    recognizer.session_stopped.connect(lambda _: done.set())
    recognizer.start_continuous_recognition()
    done.wait()
    recognizer.stop_continuous_recognition()
    if errors:
        raise RuntimeError("Speech canceló el reconocimiento: " + "; ".join(errors))
    return segments


def save_json(name: str, data: Any) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
