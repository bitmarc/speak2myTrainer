"""Página de prueba de la Fase 0: grabación en móvil y cabecera de Easy Auth.

No usa casos de uso: solo responde dos preguntas del PRD antes de construir la UI real.
  1. ¿`st.audio_input` graba bien en Safari iOS y Chrome Android?
  2. ¿La identidad de Easy Auth (`X-MS-CLIENT-PRINCIPAL*`) llega a la sesión de Streamlit?
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="speak2myTrainer · probe", page_icon="🎙️")
st.title("🎙️ Probe de la Fase 0")

headers = {k.lower(): v for k, v in st.context.headers.items()}

st.header("1 · Identidad (Easy Auth)")
name = headers.get("x-ms-client-principal-name")
if name:
    st.success(f"Sesión iniciada como **{name}**")
    st.caption(f"Proveedor: {headers.get('x-ms-client-principal-idp', '—')}")
    raw = headers.get("x-ms-client-principal")
    if raw:
        try:
            principal = json.loads(base64.b64decode(raw))
            claims = {c["typ"].rsplit("/", 1)[-1]: c["val"] for c in principal.get("claims", [])}
            st.json({k: claims[k] for k in ("emailaddress", "email", "name") if k in claims})
        except (binascii.Error, json.JSONDecodeError, KeyError) as exc:
            st.warning(f"No se pudo decodificar X-MS-CLIENT-PRINCIPAL: {exc}")
else:
    st.info("Sin cabeceras de Easy Auth (normal en local o detrás de un túnel).")

with st.expander("Dispositivo"):
    st.code(headers.get("user-agent", "—"))


def ffprobe_info(data: bytes, suffix: str) -> dict[str, str]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"error": "ffprobe no disponible"}
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = Path(tmp.name)
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration,format_name:stream=codec_name,sample_rate,channels",
             "-of", "json", str(path)],
            capture_output=True, text=True, check=True,
        )  # fmt: skip
        info = json.loads(out.stdout)
        stream = (info.get("streams") or [{}])[0]
        fmt = info.get("format", {})
        return {
            "formato": fmt.get("format_name", "?"),
            "códec": stream.get("codec_name", "?"),
            "sample rate": stream.get("sample_rate", "?"),
            "canales": str(stream.get("channels", "?")),
            "duración (s)": f"{float(fmt.get('duration', 0)):.1f}",
        }
    except subprocess.CalledProcessError as exc:
        return {"error": exc.stderr.strip()}
    finally:
        path.unlink(missing_ok=True)


st.header("2 · Grabar desde el navegador")
st.caption("Prueba también bloquear la pantalla a mitad de la grabación.")
recording = st.audio_input("Graba una respuesta", sample_rate=16000)
if recording is not None:
    data = recording.getvalue()
    with wave.open(io.BytesIO(data)) as w:
        seconds = w.getnframes() / w.getframerate()
        st.write(
            f"WAV · {w.getframerate()} Hz · {w.getnchannels()} canal(es) · "
            f"**{seconds:.1f} s** · {len(data) / 1_048_576:.2f} MB"
        )
    st.audio(data, format="audio/wav")

st.header("3 · Subir un archivo")
upload = st.file_uploader("Audio pregrabado", type=["m4a", "mp3", "wav", "ogg", "webm", "aac"])
if upload is not None:
    data = upload.getvalue()
    st.write(f"{upload.name} · {len(data) / 1_048_576:.2f} MB")
    st.table(ffprobe_info(data, Path(upload.name).suffix))
    st.audio(data)
