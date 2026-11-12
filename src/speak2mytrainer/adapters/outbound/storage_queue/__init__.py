"""Adaptador `JobQueue` sobre Azure Storage Queue. El job lo dispara KEDA por longitud de cola."""

from __future__ import annotations

import json
from dataclasses import asdict

from azure.core.credentials import TokenCredential
from azure.storage.queue import QueueClient, TextBase64DecodePolicy, TextBase64EncodePolicy

from speak2mytrainer.application.ports import AttemptJob

QUEUE_NAME = "attempts"


def queue_client(endpoint: str, credential: TokenCredential, name: str = QUEUE_NAME) -> QueueClient:
    """Cliente con mensajes en base64, la convención de Functions y de las herramientas de Azure."""
    return QueueClient(
        endpoint,
        name,
        credential=credential,
        message_encode_policy=TextBase64EncodePolicy(),
        message_decode_policy=TextBase64DecodePolicy(),
    )


def encode_job(job: AttemptJob) -> str:
    return json.dumps(asdict(job))


def decode_job(content: str) -> AttemptJob:
    return AttemptJob(**json.loads(content))


class StorageQueueJobQueue:
    def __init__(self, client: QueueClient) -> None:
        self._client = client

    def enqueue(self, job: AttemptJob) -> None:
        self._client.send_message(encode_job(job))
