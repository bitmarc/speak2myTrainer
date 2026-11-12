"""Resultado de un intento: estado en vivo mientras se procesa y los bloques del análisis."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from speak2mytrainer.adapters.inbound.streamlit_app import WebContext
from speak2mytrainer.adapters.inbound.streamlit_app.format import (
    FILLER_LABELS,
    SEVERITY_LABELS,
    STATUS_LABELS,
    escape,
    format_duration,
    highlight,
)
from speak2mytrainer.domain.metrics import INTERVIEW_WPM_RANGE
from speak2mytrainer.domain.models import Attempt, AttemptStatus, FillerType, TextAnalysis

POLL_SECONDS = 3
_STEPS = [AttemptStatus.QUEUED, AttemptStatus.TRANSCRIBING, AttemptStatus.ANALYZING]


def render_attempt(ctx: WebContext, attempt: Attempt) -> None:
    if attempt.status is AttemptStatus.DONE:
        _render_done(ctx, attempt)
    elif attempt.status is AttemptStatus.FAILED and not _will_retry(attempt):
        st.error(attempt.error or "No se pudo analizar el audio.")
        _audio(ctx, attempt)
    else:
        _progress(ctx, attempt.user_id, attempt.id)


def _will_retry(attempt: Attempt) -> bool:
    return bool(attempt.error and "reintentará" in attempt.error)


@st.fragment(run_every=POLL_SECONDS)
def _progress(ctx: WebContext, user_id: str, attempt_id: str) -> None:
    attempt = ctx.container.practices.get_attempt(user_id, attempt_id)
    if attempt is None:
        return
    if attempt.status is AttemptStatus.DONE or (
        attempt.status is AttemptStatus.FAILED and not _will_retry(attempt)
    ):
        st.rerun()  # toda la página, para pintar el resultado
    step = _STEPS.index(attempt.status) if attempt.status in _STEPS else 0
    label = STATUS_LABELS[attempt.status]
    if attempt.status is AttemptStatus.FAILED:
        label = "Hubo un problema; se reintentará en unos segundos"
    st.progress((step + 1) / (len(_STEPS) + 1), text=f"{label}…")
    st.caption(
        "El análisis tarda más o menos la mitad de lo que dura el audio. "
        "Puedes salir y volver: el resultado se guarda."
    )


def _audio(ctx: WebContext, attempt: Attempt) -> None:
    url = ctx.container.audio.signed_url(attempt.audio_blob, timedelta(minutes=15))
    # En local la "URL" es file://, que el navegador no puede abrir: se envían los bytes.
    st.audio(ctx.container.audio.read(attempt.audio_blob) if url.startswith("file:") else url)


def _render_done(ctx: WebContext, attempt: Attempt) -> None:
    analysis = attempt.analysis or TextAnalysis(improved_version="")
    metrics = attempt.metrics

    if metrics:
        low, high = INTERVIEW_WPM_RANGE
        cols = st.columns(4)
        cols[0].metric("Duración", format_duration(metrics.duration_sec))
        cols[1].metric(
            "Palabras/min", f"{metrics.wpm:.0f}", help=f"Referencia en entrevista: {low} a {high}."
        )
        cols[2].metric("Muletillas/min", f"{metrics.fillers_per_min:.1f}")
        cols[3].metric("Reinicios", metrics.restarts)

    st.subheader("Muletillas")
    if analysis.fillers:
        for filler in analysis.fillers:
            st.markdown(
                f"- {highlight(filler.quote, filler.token)} · *{FILLER_LABELS[filler.type]}*"
            )
        if any(f.type is FillerType.HESITATION for f in analysis.fillers):
            st.caption(
                "Las citas de pausas de duda vienen del reconocimiento de voz, en minúsculas."
            )
    else:
        st.write("No se detectaron muletillas.")
    if analysis.valid_non_fillers:
        with st.expander(f"Usos válidos no contados ({len(analysis.valid_non_fillers)})"):
            for valid in analysis.valid_non_fillers:
                st.markdown(f"- {highlight(valid.quote, valid.token)} — {escape(valid.reason)}")

    st.subheader("Gramática")
    if analysis.grammar:
        for issue in analysis.grammar:
            label, color = SEVERITY_LABELS[issue.severity]
            with st.container(border=True):
                st.badge(label, color=color)  # type: ignore[arg-type]
                st.markdown(f"~~{escape(issue.quote)}~~ → **{escape(issue.fix)}**")
                st.caption(issue.why)
    else:
        st.write("No se encontraron errores gramaticales.")

    st.subheader("Versión mejorada")
    st.info(analysis.improved_version or "—")

    if analysis.next_steps:
        st.subheader("Para tu próximo intento")
        st.markdown("\n".join(f"{i}. {escape(s)}" for i, s in enumerate(analysis.next_steps, 1)))

    with st.expander("Transcripción y audio"):
        st.write(attempt.transcript or "—")
        _audio(ctx, attempt)
