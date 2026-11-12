"""Adaptador de entrada web (Streamlit): traduce la sesión y los clics a casos de uso.

La identidad llega de Easy Auth en la cabecera `X-MS-CLIENT-PRINCIPAL-NAME` (ADR 0004); en
local, de `S2MT_DEV_USER`. El punto de entrada es `speak2mytrainer.entrypoints.web`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from speak2mytrainer.application.container import Container


@dataclass(frozen=True)
class WebContext:
    container: Container
    # Usuario de la sesión cuando no hay Easy Auth delante (desarrollo local).
    dev_user: str | None = None
    # En local no hay job: el punto de entrada procesa la cola en memoria después de enviar.
    after_submit: Callable[[], None] | None = None


def run(ctx: WebContext) -> None:
    from speak2mytrainer.adapters.inbound.streamlit_app.app import run as _run

    _run(ctx)
