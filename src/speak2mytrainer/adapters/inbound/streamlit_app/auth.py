"""Identidad de la sesión: Easy Auth delante de la app, o el usuario de desarrollo en local."""

from __future__ import annotations

import base64
import binascii
import json

import streamlit as st

from speak2mytrainer.adapters.inbound.streamlit_app import WebContext
from speak2mytrainer.application.use_cases.access import resolve_user
from speak2mytrainer.domain.errors import NotAllowedError
from speak2mytrainer.domain.models import UserProfile

LOGOUT_URL = "/.auth/logout"


def _display_name(principal: str | None) -> str | None:
    """Nombre del claim `name` dentro de X-MS-CLIENT-PRINCIPAL (JSON en base64)."""
    if not principal:
        return None
    try:
        claims = json.loads(base64.b64decode(principal)).get("claims", [])
    except (binascii.Error, json.JSONDecodeError, AttributeError):
        return None
    for claim in claims:
        if claim.get("typ", "").rsplit("/", 1)[-1] == "name":
            return str(claim.get("val"))
    return None


def has_easy_auth() -> bool:
    return "x-ms-client-principal-name" in {k.lower() for k in st.context.headers}


def current_user(ctx: WebContext) -> UserProfile:
    """Usuario permitido de la sesión; si no lo hay, muestra el motivo y detiene la página."""
    headers = {k.lower(): v for k, v in st.context.headers.items()}
    email = headers.get("x-ms-client-principal-name") or ctx.dev_user
    if not email:
        st.error("No hay una sesión iniciada. Vuelve a abrir la app para iniciar sesión.")
        st.stop()
    name = _display_name(headers.get("x-ms-client-principal"))
    try:
        return resolve_user(ctx.container.users, email, name, ctx.container.admin_email)
    except NotAllowedError:
        st.title("Acceso restringido")
        st.write(
            f"Tu cuenta **{email}** no está en la lista de usuarios permitidos. "
            "Pide acceso al administrador."
        )
        if has_easy_auth():
            st.link_button("Cerrar sesión", LOGOUT_URL)
        st.stop()
