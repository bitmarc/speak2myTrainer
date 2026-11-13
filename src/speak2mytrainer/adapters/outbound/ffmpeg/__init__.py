"""Adaptador `AudioConverter` con ffmpeg y ffprobe (incluidos en la imagen de Docker)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from functools import cache
from pathlib import Path

from speak2mytrainer.domain.errors import UnsupportedAudioError


@cache
def _tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    # En Windows, `winget install Gyan.FFmpeg` deja el ejecutable en esta carpeta.
    link = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / name
    if link.with_suffix(".exe").exists():
        return str(link.with_suffix(".exe"))
    raise RuntimeError(f"No se encontró {name}; instala ffmpeg.")


class FfmpegAudioConverter:
    def _run(self, args: list[str]) -> str:
        try:
            out = subprocess.run(args, check=True, capture_output=True, text=True, timeout=300)
        except subprocess.CalledProcessError as exc:
            raise UnsupportedAudioError(
                "No se pudo leer el audio; prueba con otro archivo o graba de nuevo."
            ) from exc
        return out.stdout

    def duration_sec(self, data: bytes, suffix: str) -> float:
        # Archivo temporal y no stdin: el .m4a del iPhone guarda el índice al final y
        # ffprobe necesita poder saltar dentro del archivo.
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"input{suffix}"
            src.write_bytes(data)
            out = self._run(
                [_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(src)]
            )  # fmt: skip
        try:
            return float(out.strip())
        except ValueError as exc:
            raise UnsupportedAudioError("El archivo no parece contener audio.") from exc

    def to_m4a(self, data: bytes, suffix: str) -> bytes:
        # 48 kbps mono basta para voz (~0.35 MB/min frente a ~2 MB/min del WAV). `faststart`
        # pone el índice al principio para que Safari empiece a reproducir sin bajar todo.
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"input{suffix}"
            dst = Path(tmp) / "output.m4a"
            src.write_bytes(data)
            self._run(
                [_tool("ffmpeg"), "-y", "-loglevel", "error", "-i", str(src), "-vn",
                 "-ac", "1", "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart", str(dst)]
            )  # fmt: skip
            return dst.read_bytes()

    def to_wav16k(self, data: bytes, suffix: str, dst: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"input{suffix}"
            src.write_bytes(data)
            self._run(
                [_tool("ffmpeg"), "-y", "-loglevel", "error", "-i", str(src),
                 "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(dst)]
            )  # fmt: skip
