"""Página de una práctica: sus intentos, el resultado y la grabación de un intento nuevo."""

from __future__ import annotations

import streamlit as st

from speak2mytrainer.adapters.inbound.streamlit_app import WebContext
from speak2mytrainer.adapters.inbound.streamlit_app.format import (
    STATUS_LABELS,
    escape,
    format_date,
)
from speak2mytrainer.adapters.inbound.streamlit_app.nav import Nav
from speak2mytrainer.adapters.inbound.streamlit_app.result import (
    HIDE_IMPROVED_KEY,
    HIDE_IMPROVED_WIDGET,
    new_attempt_key,
    render_attempt,
)
from speak2mytrainer.application.use_cases.practices import delete_practice
from speak2mytrainer.domain.errors import DomainError
from speak2mytrainer.domain.metrics import MAX_DURATION_SEC, MIN_DURATION_SEC
from speak2mytrainer.domain.models import Practice, UserProfile, utcnow

UPLOAD_TYPES = ["m4a", "mp3", "wav", "ogg", "webm", "aac"]
ASSESS_KEY = "assess-pronunciation"


def practice_page(ctx: WebContext, user: UserProfile, nav: Nav) -> None:
    practice_id = st.query_params.get("id", "")
    practice = ctx.container.practices.get_practice(user.id, practice_id)
    if practice is None:
        st.warning("La práctica no existe o fue borrada.")
        assert nav.practices is not None
        st.page_link(nav.practices, label="Volver a mis prácticas", icon=":material/arrow_back:")
        return

    st.title(practice.title)
    if practice.context:
        st.caption(escape(practice.context))

    attempts = ctx.container.practices.list_attempts(user.id, practice.id)
    if attempts:
        by_id = {a.id: a for a in attempts}
        selected = st.query_params.get("intento")
        if selected not in by_id:
            selected = attempts[-1].id
        choice = st.selectbox(
            "Intento",
            list(by_id),
            index=list(by_id).index(selected),
            format_func=lambda i: (
                f"Intento {by_id[i].number} · {STATUS_LABELS[by_id[i].status]} · "
                f"{format_date(by_id[i].created_at)}"
            ),
        )
        if choice != st.query_params.get("intento"):
            st.query_params["intento"] = choice
        render_attempt(ctx, by_id[choice])
        st.divider()

    open_key = new_attempt_key(practice.id)
    if not attempts or st.session_state.get(open_key):
        _recorder(ctx, user, practice, first=not attempts)
    elif st.button("Nuevo intento", type="primary", icon=":material/mic:"):
        st.session_state[open_key] = True
        st.rerun()
    _danger_zone(ctx, user, practice, nav)


def _recorder(ctx: WebContext, user: UserProfile, practice: Practice, *, first: bool) -> None:
    st.subheader("Graba tu respuesta" if first else "Nuevo intento")
    open_key = new_attempt_key(practice.id)
    if not first:
        st.session_state[HIDE_IMPROVED_KEY] = st.toggle(
            "Ocultar la versión mejorada mientras grabo",
            value=st.session_state.get(HIDE_IMPROVED_KEY, True),
            key=HIDE_IMPROVED_WIDGET,
        )
    quota = user.quota.model_copy()
    quota.roll_over_if_needed(utcnow())
    st.caption(
        f"Entre {MIN_DURATION_SEC:.0f} s y {MAX_DURATION_SEC / 60:.0f} min. "
        f"Te quedan {quota.remaining_minutes():.1f} min este mes."
    )

    # Cambiar la clave de los widgets los vacía: así funciona "Reintentar".
    nonce = st.session_state.setdefault("recorder_nonce", 0)
    record_tab, upload_tab = st.tabs(["Grabar", "Subir archivo"])
    with record_tab:
        recording = st.audio_input("Grabación", key=f"rec-{nonce}", label_visibility="collapsed")
    with upload_tab:
        upload = st.file_uploader(
            "Audio pregrabado", type=UPLOAD_TYPES, key=f"up-{nonce}", label_visibility="collapsed"
        )
        if upload is not None:
            st.audio(upload)

    # Se recuerda en la sesión aparte del widget, que se vacía con cada grabación nueva.
    st.session_state[ASSESS_KEY] = st.checkbox(
        "Evaluar también la pronunciación",
        value=st.session_state.get(ASSESS_KEY, False),
        key=f"assess-{nonce}",
        help="Puntajes de pronunciación, fluidez y prosodia, y palabras a practicar. "
        "El análisis tarda más o menos el doble.",
    )

    audio = recording or upload
    if audio is None:
        if not first and st.button("Cancelar"):
            st.session_state[open_key] = False
            st.rerun()
        return
    left, right = st.columns(2)
    if left.button("Enviar para análisis", type="primary", use_container_width=True):
        filename = upload.name if audio is upload and upload else "grabacion.wav"
        with st.spinner("Enviando…"):
            try:
                attempt = ctx.container.submit_attempt(
                    user.id,
                    practice.id,
                    audio.getvalue(),
                    filename,
                    assess_pronunciation=bool(st.session_state[ASSESS_KEY]),
                )
            except DomainError as exc:
                st.error(str(exc))
                return
            if ctx.after_submit:
                ctx.after_submit()
        st.session_state["recorder_nonce"] = nonce + 1
        st.session_state[open_key] = False
        st.query_params["intento"] = attempt.id
        st.rerun()
    if right.button(
        "Reintentar",
        help="Descarta esta grabación sin guardarla ni gastar minutos.",
        use_container_width=True,
    ):
        st.session_state["recorder_nonce"] = nonce + 1
        st.rerun()


def _danger_zone(ctx: WebContext, user: UserProfile, practice: Practice, nav: Nav) -> None:
    with st.expander("Borrar práctica"):
        st.caption("Borra la práctica, sus intentos y sus audios. No se puede deshacer.")
        confirmed = st.checkbox("Sí, quiero borrarla", key=f"confirm-{practice.id}")
        if st.button("Borrar práctica", disabled=not confirmed):
            delete_practice(ctx.container.practices, ctx.container.audio, user.id, practice.id)
            nav.go(nav.practices)
