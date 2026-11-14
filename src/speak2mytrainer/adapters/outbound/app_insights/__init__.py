"""Adaptador `Telemetry` con OpenTelemetry, exportado a Application Insights (ADR 0005).

`configure` se llama una vez por proceso desde el entrypoint. Sin configurar, OpenTelemetry usa
su proveedor vacío y los tramos no cuestan nada, así que el adaptador funciona igual en local.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from azure.core.credentials import TokenCredential
from opentelemetry import trace

from speak2mytrainer.application.ports import Attribute

_TRACER_NAME = "speak2mytrainer"

# Las dependencias automáticas de Cosmos y Blob llevan en el nombre y la URL el id del
# documento o la ruta del blob, que incluyen el correo del usuario: se apagan. Los tramos
# propios ya miden cada paso. Se deja httpx, que solo ve la llamada a Azure OpenAI.
_INSTRUMENTATION = {
    name: {"enabled": False} for name in ("azure_sdk", "requests", "urllib", "urllib3")
}


def configure(
    connection_string: str, credential: TokenCredential, service: str, *, tracing: bool
) -> None:
    """Exporta logs (y trazas si `tracing`) a Application Insights con un token de Entra.

    La web solo exporta logs: Streamlit consulta Cosmos cada pocos segundos y cada lectura
    sería una dependencia, mucho volumen sin valor. El job exporta trazas, una por intento.
    """
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry.sdk.resources import Resource

    # El distro ignora `disable_tracing` y `disable_metrics` como argumentos: los lee de las
    # variables estándar de OpenTelemetry. Su muestreo por defecto (5 trazas/s, adaptativo)
    # descartó la traza del primer intento en Azure; con un intento cada tanto, se guardan todas.
    os.environ["OTEL_METRICS_EXPORTER"] = "none"  # las métricas estándar gastan ingesta
    os.environ["OTEL_TRACES_EXPORTER"] = "azure_monitor" if tracing else "none"
    os.environ["OTEL_TRACES_SAMPLER"] = "always_on"
    configure_azure_monitor(
        connection_string=connection_string,
        credential=credential,
        resource=Resource.create({"service.name": service}),
        enable_live_metrics=False,
        enable_performance_counters=False,
        instrumentation_options=_INSTRUMENTATION,
    )


def flush() -> None:
    """Envía lo pendiente antes de que termine el proceso (el job vive pocos minutos)."""
    provider = trace.get_tracer_provider()
    force_flush = getattr(provider, "force_flush", None)
    if force_flush is not None:
        force_flush()


class OpenTelemetryTelemetry:
    def __init__(self) -> None:
        self._tracer = trace.get_tracer(_TRACER_NAME)

    @contextmanager
    def span(self, name: str, **attributes: Attribute) -> Iterator[None]:
        # Una excepción dentro del tramo queda registrada en él con estado de error.
        with self._tracer.start_as_current_span(name, attributes=attributes):
            yield

    def annotate(self, **attributes: Attribute) -> None:
        trace.get_current_span().set_attributes(attributes)
