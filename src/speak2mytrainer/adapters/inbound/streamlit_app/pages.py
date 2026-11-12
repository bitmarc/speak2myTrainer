"""Páginas generales: historial, nueva práctica, preferencias y administración."""

from __future__ import annotations

import streamlit as st

from speak2mytrainer.adapters.inbound.streamlit_app import WebContext
from speak2mytrainer.adapters.inbound.streamlit_app.format import format_date
from speak2mytrainer.adapters.inbound.streamlit_app.nav import Nav
from speak2mytrainer.application.use_cases import access
from speak2mytrainer.application.use_cases.practices import create_practice, delete_history
from speak2mytrainer.domain.errors import DomainError
from speak2mytrainer.domain.models import Role, UserProfile, utcnow

CONFIRM_WORD = "BORRAR"


def practices(ctx: WebContext, user: UserProfile, nav: Nav) -> None:
    st.title("Mis prácticas")
    assert nav.new_practice is not None and nav.practice is not None
    st.page_link(nav.new_practice, label="Nueva práctica", icon=":material/add_circle:")

    items = ctx.container.practices.list_practices(user.id)
    if not items:
        st.info(
            "Aún no tienes prácticas. Crea una con la pregunta o el tema que quieres practicar."
        )
        return
    for item in items:
        with st.container(border=True):
            st.page_link(nav.practice, label=f"**{item.title}**", query_params={"id": item.id})
            when = format_date(item.last_attempt_at or item.created_at)
            st.caption(f"{item.attempt_count} intento(s) · {when}")


def new_practice(ctx: WebContext, user: UserProfile, nav: Nav) -> None:
    st.title("Nueva práctica")
    with st.form("new-practice"):
        title = st.text_input("Título", placeholder="Entrevista: Tell me about yourself")
        context = st.text_area(
            "Contexto (opcional)",
            placeholder=(
                "Entrevista para backend developer remoto. "
                "Pregunta: Tell me about a challenging project you worked on."
            ),
            help="La pregunta, el tema o la situación. Ayuda a que el análisis sea más preciso.",
        )
        submitted = st.form_submit_button("Crear práctica", type="primary")
    if submitted:
        try:
            created = create_practice(ctx.container.practices, user.id, title, context)
        except ValueError as exc:
            st.error(str(exc))
        else:
            nav.go(nav.practice, id=created.id)


def preferences(ctx: WebContext, user: UserProfile) -> None:
    st.title("Preferencias")

    languages = list(access.FEEDBACK_LANGUAGES)
    language = st.radio(
        "Idioma de las explicaciones",
        languages,
        index=languages.index(user.feedback_language),
        format_func=access.FEEDBACK_LANGUAGES.__getitem__,
        horizontal=True,
        help="El idioma practicado es inglés; esto cambia el idioma de las explicaciones.",
    )
    if language != user.feedback_language:
        access.set_feedback_language(ctx.container.users, user.id, language)
        st.toast("Preferencia guardada")

    st.subheader("Cuota del mes")
    quota = user.quota.model_copy()
    quota.roll_over_if_needed(utcnow())
    used, limit = quota.used_this_month, quota.minutes_per_month
    st.progress(min(used / limit, 1.0) if limit else 1.0, text=f"{used:.1f} de {limit:.0f} min")

    st.subheader("Borrar mi historial")
    st.caption("Borra todas tus prácticas, intentos y audios. No se puede deshacer.")
    confirm = st.text_input(f"Escribe {CONFIRM_WORD} para confirmar", key="confirm-delete")
    if st.button("Borrar todo", type="primary", disabled=confirm != CONFIRM_WORD):
        delete_history(ctx.container.practices, ctx.container.audio, user.id)
        st.success("Tu historial se borró.")


def admin(ctx: WebContext, user: UserProfile) -> None:
    st.title("Administración")
    users = ctx.container.users

    st.subheader("Usuarios")
    rows = [
        {
            "Correo": u.id,
            "Rol": "admin" if u.role is Role.ADMIN else "usuario",
            "Acceso": "sí" if u.allowed else "no",
            "Cuota (min)": u.quota.minutes_per_month,
            "Usado (min)": round(u.quota.used_this_month, 1),
        }
        for u in access.list_users(users, user)
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)

    st.subheader("Dar acceso")
    with st.form("allow-user", clear_on_submit=True):
        email = st.text_input("Correo de Google")
        minutes = st.number_input("Minutos al mes", min_value=0, value=60, step=10)
        if st.form_submit_button("Agregar", type="primary"):
            try:
                access.allow_user(users, user, email, float(minutes))
            except (ValueError, DomainError) as exc:
                st.error(str(exc))
            else:
                st.rerun()

    others = [r["Correo"] for r in rows if r["Correo"] != user.id]
    if not others:
        return
    st.subheader("Editar usuario")
    selected = st.selectbox("Usuario", others)
    target = users.get(str(selected))
    if target is None:
        return
    minutes = st.number_input(
        "Minutos al mes", min_value=0, value=int(target.quota.minutes_per_month), step=10,
        key=f"quota-{target.id}",
    )  # fmt: skip
    left, right = st.columns(2)
    if left.button("Guardar cuota", use_container_width=True):
        access.set_quota(users, user, target.id, float(minutes))
        st.rerun()
    if target.allowed:
        if right.button("Quitar acceso", use_container_width=True):
            access.revoke_user(users, user, target.id)
            st.rerun()
    elif right.button("Devolver acceso", use_container_width=True):
        access.allow_user(users, user, target.id)
        st.rerun()
