"""Resultado de un intento: estado en vivo mientras se procesa y los bloques del análisis."""

from __future__ import annotations

import html
import logging
from datetime import timedelta

import streamlit as st

from speak2mytrainer.adapters.inbound.streamlit_app import WebContext
from speak2mytrainer.adapters.inbound.streamlit_app.format import (
    FILLER_LABELS,
    SCORE_HELP,
    SEVERITY_LABELS,
    STATUS_LABELS,
    escape,
    format_duration,
    highlight,
)
from speak2mytrainer.application.use_cases.practices import improved_audio, tts_path
from speak2mytrainer.domain.errors import DomainError
from speak2mytrainer.domain.metrics import INTERVIEW_WPM_RANGE
from speak2mytrainer.domain.models import (
    Attempt,
    AttemptStatus,
    Comparison,
    FillerType,
    Metrics,
    TextAnalysis,
)

POLL_SECONDS = 3
# Preferencia de la sesión y clave del interruptor. Se separan porque Streamlit borra el estado
# de un widget cuando deja de mostrarse (el grabador se cierra al enviar).
HIDE_IMPROVED_KEY = "hide-improved"
HIDE_IMPROVED_WIDGET = "hide-improved-widget"

_log = logging.getLogger(__name__)


def new_attempt_key(practice_id: str) -> str:
    """Clave de sesión: el usuario abrió "Nuevo intento" en esta práctica."""
    return f"new-attempt-{practice_id}"


def improved_hidden(practice_id: str) -> bool:
    """La versión mejorada se difumina mientras se graba un intento nuevo (RF-17)."""
    if not st.session_state.get(new_attempt_key(practice_id)):
        return False
    preference = st.session_state.get(HIDE_IMPROVED_KEY, True)
    return bool(st.session_state.get(HIDE_IMPROVED_WIDGET, preference))


def _steps(attempt: Attempt) -> list[AttemptStatus]:
    steps = [AttemptStatus.QUEUED, AttemptStatus.TRANSCRIBING]
    if attempt.assess_pronunciation:
        steps.append(AttemptStatus.ASSESSING)
    return [*steps, AttemptStatus.ANALYZING]


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
    steps = _steps(attempt)
    step = steps.index(attempt.status) if attempt.status in steps else 0
    label = STATUS_LABELS[attempt.status]
    if attempt.status is AttemptStatus.FAILED:
        label = "Hubo un problema; se reintentará en unos segundos"
    st.progress((step + 1) / (len(steps) + 1), text=f"{label}…")
    pace = "lo mismo" if attempt.assess_pronunciation else "la mitad de lo"
    st.caption(
        f"El análisis tarda más o menos {pace} que dura el audio. "
        "Puedes salir y volver: el resultado se guarda."
    )


def _audio(ctx: WebContext, attempt: Attempt) -> None:
    _play(ctx, attempt.audio_blob)


def _play(ctx: WebContext, path: str, mime: str = "audio/wav") -> None:
    url = ctx.container.audio.signed_url(path, timedelta(minutes=15))
    # En local la "URL" es file://, que el navegador no puede abrir: se envían los bytes.
    if url.startswith("file:"):
        st.audio(ctx.container.audio.read(path), format=mime)
    else:
        st.audio(url)


def _improved(ctx: WebContext, attempt: Attempt, text: str) -> None:
    st.subheader("Versión mejorada")
    if improved_hidden(attempt.practice_id):
        st.markdown(
            '<div aria-hidden="true" style="filter: blur(6px); user-select: none; '
            f'-webkit-user-select: none; padding: 0.75rem 1rem;">{html.escape(text)}</div>',
            unsafe_allow_html=True,
        )
        st.caption("Oculta mientras grabas el nuevo intento.")
        return
    st.info(text or "—")
    if text.strip():
        _listen(ctx, attempt)


def _listen(ctx: WebContext, attempt: Attempt) -> None:
    """Escuchar la versión mejorada (RF-16): se genera al primer clic y queda en caché."""
    user = ctx.container.users.get(attempt.user_id)
    if user is None:
        return
    if attempt.tts_blob == tts_path(user, attempt):
        _play(ctx, attempt.tts_blob, "audio/mpeg")
        return
    if not st.button("Escuchar", icon=":material/volume_up:", key=f"tts-{attempt.id}"):
        return
    with st.spinner("Generando el audio…"):
        try:
            path = improved_audio(
                ctx.container.practices,
                ctx.container.audio,
                ctx.container.synthesizer,
                user,
                attempt.id,
                ctx.container.prices,
            )
        except DomainError as exc:
            st.error(str(exc))
            return
        except Exception:
            _log.exception("No se pudo generar el TTS del intento %s", attempt.id)
            st.error("No se pudo generar el audio. Intenta más tarde.")
            return
    _play(ctx, path, "audio/mpeg")


def _delta(current: float | None, before: Metrics | None, field: str, digits: int) -> str | None:
    """Diferencia contra el intento anterior, calculada en Python; None si no hay con qué."""
    previous = getattr(before, field) if before else None
    if current is None or previous is None:
        return None
    text = f"{current - previous:+.{digits}f}"
    # Sin cambio no se muestra nada: un "+0" en rojo o verde confunde.
    return None if float(text) == 0 else text


def _metrics(metrics: Metrics, before: Metrics | None) -> None:
    low, high = INTERVIEW_WPM_RANGE
    cols = st.columns(4)
    cols[0].metric("Duración", format_duration(metrics.duration_sec))
    cols[1].metric(
        "Palabras/min",
        f"{metrics.wpm:.0f}",
        delta=_delta(metrics.wpm, before, "wpm", 0),
        delta_color="off",  # más rápido no es mejor ni peor por sí solo
        help=f"Referencia en entrevista: {low} a {high}.",
    )
    cols[2].metric(
        "Muletillas/min",
        f"{metrics.fillers_per_min:.1f}",
        delta=_delta(metrics.fillers_per_min, before, "fillers_per_min", 1),
        delta_color="inverse",
    )
    cols[3].metric(
        "Reinicios",
        metrics.restarts,
        delta=_delta(metrics.restarts, before, "restarts", 0),
        delta_color="inverse",
    )
    if metrics.pron_score is None:
        return
    cols = st.columns(4)
    scores = [
        ("Pronunciación", "pron_score"),
        ("Precisión", "accuracy"),
        ("Fluidez", "fluency"),
        ("Prosodia", "prosody"),
    ]
    for col, (label, field) in zip(cols, scores, strict=True):
        value = getattr(metrics, field)
        if value is not None:
            col.metric(
                label,
                f"{value:.0f}",
                delta=_delta(value, before, field, 0),
                help=SCORE_HELP[field],
            )


def _comparison(comparison: Comparison) -> None:
    st.subheader(f"Comparado con el intento {comparison.previous_attempt_number}")
    lines = [f"- :green[✓] {escape(item)}" for item in comparison.fixed]
    lines += [f"- :red[✗] {escape(item)}" for item in comparison.regressed]
    if lines:
        st.markdown("\n".join(lines))
    if comparison.adopted_suggestions:
        st.markdown(
            "**Sugerencias que aplicaste:** "
            + "; ".join(escape(s) for s in comparison.adopted_suggestions)
        )
    st.caption(f"Muletillas: {comparison.fillers_before} → {comparison.fillers_after}.")


def _pronunciation(attempt: Attempt) -> None:
    assert attempt.pronunciation is not None
    st.subheader("Pronunciación")
    issues = attempt.pronunciation.issues
    if not issues:
        st.write("No hay palabras con problemas claros de pronunciación.")
        return
    for issue in issues:
        sounds = " ".join(f"/{p}/" for p in issue.weak_phonemes)
        detail = f" · sonidos débiles: {escape(sounds)}" if sounds else ""
        st.markdown(f"- **{escape(issue.word)}** · {issue.score:.0f}/100{detail}")
    st.caption(
        "Solo se muestran palabras que la transcripción confirma; las que el reconocimiento "
        "pudo entender mal se omiten."
    )


def _previous_metrics(ctx: WebContext, attempt: Attempt) -> Metrics | None:
    comparison = attempt.analysis.comparison if attempt.analysis else None
    if comparison is None or comparison.previous_attempt_number is None:
        return None
    for other in ctx.container.practices.list_attempts(attempt.user_id, attempt.practice_id):
        if other.number == comparison.previous_attempt_number:
            return other.metrics
    return None


def _render_done(ctx: WebContext, attempt: Attempt) -> None:
    analysis = attempt.analysis or TextAnalysis(improved_version="")
    if attempt.metrics:
        _metrics(attempt.metrics, _previous_metrics(ctx, attempt))

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

    if attempt.pronunciation is not None:
        _pronunciation(attempt)

    _improved(ctx, attempt, analysis.improved_version)

    if analysis.comparison is not None:
        _comparison(analysis.comparison)

    if analysis.next_steps:
        st.subheader("Para tu próximo intento")
        st.markdown("\n".join(f"{i}. {escape(s)}" for i, s in enumerate(analysis.next_steps, 1)))

    with st.expander("Transcripción y audio"):
        st.write(attempt.transcript or "—")
        _audio(ctx, attempt)
