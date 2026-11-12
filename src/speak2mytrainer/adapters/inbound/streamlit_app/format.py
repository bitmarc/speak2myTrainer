"""Textos y formatos de la interfaz (en español)."""

from __future__ import annotations

import re
from datetime import datetime

from speak2mytrainer.domain.models import AttemptStatus, FillerType, Severity

STATUS_LABELS = {
    AttemptStatus.QUEUED: "En cola",
    AttemptStatus.TRANSCRIBING: "Transcribiendo",
    AttemptStatus.ASSESSING: "Evaluando pronunciación",
    AttemptStatus.ANALYZING: "Analizando",
    AttemptStatus.DONE: "Listo",
    AttemptStatus.FAILED: "Error",
}

FILLER_LABELS = {
    FillerType.HESITATION: "Pausa de duda",
    FillerType.RESTART: "Reinicio",
    FillerType.LEXICAL: "Muletilla léxica",
}

SEVERITY_LABELS = {
    Severity.ERROR: ("Error", "red"),
    Severity.SUGGESTION: ("Sugerencia", "orange"),
    Severity.STYLE: ("Estilo", "blue"),
}

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+\-.!|~$])")


def escape(text: str) -> str:
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def highlight(quote: str, token: str) -> str:
    """La cita con la primera aparición del token en negritas (markdown escapado)."""
    match = re.search(rf"(?<!\w){re.escape(token)}(?!\w)", quote, re.IGNORECASE)
    if not match:
        return escape(quote)
    start, end = match.span()
    return f"{escape(quote[:start])}**{escape(quote[start:end])}**{escape(quote[end:])}"


def format_duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d}"


def format_date(moment: datetime) -> str:
    return moment.strftime("%d/%m/%Y %H:%M UTC")
