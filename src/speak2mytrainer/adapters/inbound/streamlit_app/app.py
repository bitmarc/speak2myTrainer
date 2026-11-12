"""Navegación de la app. Cada página es una función; la práctica se abre por `?id=`."""

from __future__ import annotations

import streamlit as st

from speak2mytrainer.adapters.inbound.streamlit_app import WebContext, pages, practice
from speak2mytrainer.adapters.inbound.streamlit_app.auth import (
    LOGOUT_URL,
    current_user,
    has_easy_auth,
)
from speak2mytrainer.adapters.inbound.streamlit_app.nav import Nav
from speak2mytrainer.domain.models import Role, UserProfile


def run(ctx: WebContext) -> None:
    user = current_user(ctx)
    nav = Nav()
    nav.practices = st.Page(
        lambda: pages.practices(ctx, user, nav),
        title="Mis prácticas",
        icon=":material/history:",
        url_path="practicas",
        default=True,
    )
    nav.new_practice = st.Page(
        lambda: pages.new_practice(ctx, user, nav),
        title="Nueva práctica",
        icon=":material/add_circle:",
        url_path="nueva",
    )
    nav.practice = st.Page(
        lambda: practice.practice_page(ctx, user, nav),
        title="Práctica",
        icon=":material/mic:",
        url_path="practica",
        visibility="hidden",
    )
    preferences = st.Page(
        lambda: pages.preferences(ctx, user),
        title="Preferencias",
        icon=":material/settings:",
        url_path="preferencias",
    )
    all_pages = [nav.practices, nav.new_practice, nav.practice, preferences]
    if user.role is Role.ADMIN:
        all_pages.append(
            st.Page(
                lambda: pages.admin(ctx, user),
                title="Admin",
                icon=":material/admin_panel_settings:",
                url_path="admin",
            )
        )
    _sidebar(user)
    st.navigation(all_pages, position="top").run()


def _sidebar(user: UserProfile) -> None:
    with st.sidebar:
        st.caption(f"Sesión: {user.id}")
        if has_easy_auth():
            st.link_button("Cerrar sesión", LOGOUT_URL, icon=":material/logout:")
