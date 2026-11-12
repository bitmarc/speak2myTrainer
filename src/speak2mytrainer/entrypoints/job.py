"""Punto de entrada del Container Apps Job:  python -m speak2mytrainer.entrypoints.job"""

from __future__ import annotations

import logging
import sys

from speak2mytrainer.adapters.inbound import worker_job
from speak2mytrainer.adapters.outbound.storage_queue import queue_client
from speak2mytrainer.bootstrap import AzureSettings, Environment, Settings, build_container


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(message)s"
    )
    settings = Settings()
    if settings.env is not Environment.AZURE:
        logging.error("El job necesita S2MT_ENV=azure (lee la cola real).")
        return 2

    from azure.identity import DefaultAzureCredential

    container = build_container(settings)
    # Los SDK de Azure y de OpenAI (httpx) registran cada petición HTTP en INFO. Se silencian
    # después de construir el contenedor porque importar `openai` reconfigura su logger.
    for noisy in ("azure", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    source = queue_client(AzureSettings().azure_storage_queue_endpoint, DefaultAzureCredential())
    processed = worker_job.run(container, source)
    logging.info("Mensajes procesados: %d", processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
