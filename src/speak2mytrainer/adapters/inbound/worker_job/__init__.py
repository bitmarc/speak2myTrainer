"""Adaptador de entrada del Container Apps Job: toma intentos de la cola y los procesa.

KEDA arranca una ejecución cuando hay mensajes. Cada ejecución vacía la cola en serie
(Speech F0 admite una solicitud a la vez) y termina. Reintentos:

- primera entrega que falla: el mensaje vuelve a la cola en `RETRY_DELAY_SEC`;
- segunda entrega (`final`): si falla, el intento queda `failed` y se devuelve la cuota;
- más entregas: el job murió sin poder marcar nada, así que se abandona sin procesar.
"""

from __future__ import annotations

import logging

from azure.storage.queue import QueueClient

from speak2mytrainer.adapters.outbound.storage_queue import decode_job
from speak2mytrainer.application.container import Container

log = logging.getLogger(__name__)

# Más que el peor caso (audio de 10 min a ~0.5x más el LLM) para que el mensaje no reaparezca
# mientras se procesa.
VISIBILITY_TIMEOUT_SEC = 20 * 60
RETRY_DELAY_SEC = 30
MAX_DELIVERIES = 2


def process_next(container: Container, source: QueueClient) -> bool:
    """Procesa un mensaje. Devuelve False si la cola estaba vacía."""
    message = source.receive_message(visibility_timeout=VISIBILITY_TIMEOUT_SEC)
    if message is None:
        return False
    job = decode_job(message.content)
    deliveries = message.dequeue_count or 1
    log.info("Intento %s, entrega %d", job.attempt_id, deliveries)

    if deliveries > MAX_DELIVERIES:
        container.process_attempt.abandon(job, "El análisis se interrumpió varias veces.")
        source.delete_message(message)
        return True

    final = deliveries == MAX_DELIVERIES
    try:
        container.process_attempt(job, final=final)
    except Exception:
        log.exception("Falló el intento %s (final=%s)", job.attempt_id, final)
        if final:
            source.delete_message(message)
        else:
            source.update_message(message, visibility_timeout=RETRY_DELAY_SEC)
        return True
    source.delete_message(message)
    log.info("Intento %s listo", job.attempt_id)
    return True


def run(container: Container, source: QueueClient, max_messages: int = 20) -> int:
    """Vacía la cola (hasta `max_messages`) y devuelve cuántos mensajes procesó."""
    processed = 0
    while processed < max_messages and process_next(container, source):
        processed += 1
    return processed
