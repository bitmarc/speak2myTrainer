"""Punto de entrada de la web:  streamlit run src/speak2mytrainer/entrypoints/web.py

Con S2MT_ENV=azure usa los servicios reales (en Container Apps, detrás de Easy Auth). En local
usa los fakes, entra como el usuario de desarrollo y procesa cada intento al enviarlo.
"""

from __future__ import annotations

import streamlit as st

from speak2mytrainer.adapters.inbound import streamlit_app
from speak2mytrainer.adapters.outbound.fakes import InMemoryJobQueue
from speak2mytrainer.application.container import Container
from speak2mytrainer.bootstrap import AzureSettings, Environment, Settings, build_container

st.set_page_config(page_title="speak2myTrainer", page_icon="🎙️", layout="centered")


def _drain_local_queue(container: Container) -> None:
    queue = container.queue
    if isinstance(queue, InMemoryJobQueue):
        while queue.jobs:
            container.process_attempt(queue.jobs.popleft(), final=True)


def _configure_telemetry() -> None:
    """Solo logs y excepciones (ADR 0005); las trazas por intento son del job."""
    azure = AzureSettings()
    if not azure.applicationinsights_connection_string:
        return
    from azure.identity import DefaultAzureCredential

    from speak2mytrainer.adapters.outbound import app_insights

    app_insights.configure(
        azure.applicationinsights_connection_string,
        DefaultAzureCredential(),
        "s2mt-web",
        tracing=False,
    )


@st.cache_resource(show_spinner=False)
def _context() -> streamlit_app.WebContext:
    settings = Settings()
    if settings.env is Environment.AZURE:
        _configure_telemetry()
        return streamlit_app.WebContext(build_container(settings), dev_user=settings.dev_user)
    dev_user = settings.dev_user or settings.admin_email or "dev@local"
    settings = settings.model_copy(update={"admin_email": settings.admin_email or dev_user})
    container = build_container(settings)
    return streamlit_app.WebContext(
        container, dev_user=dev_user, after_submit=lambda: _drain_local_queue(container)
    )


streamlit_app.run(_context())
