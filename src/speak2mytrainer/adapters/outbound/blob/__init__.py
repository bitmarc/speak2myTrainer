"""Adaptador `AudioStorage` sobre Blob Storage, sin shared key.

Las rutas del núcleo empiezan por el contenedor (`audio/...`, `tts/...`). Las URLs firmadas son
SAS de delegación de usuario, firmadas con la identidad de la app y no con una llave.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from azure.core.credentials import TokenCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    UserDelegationKey,
    generate_blob_sas,
)

# La clave de delegación vale hasta 7 días; se renueva cada 6 horas.
_KEY_LIFETIME = timedelta(hours=6)


def _split(path: str) -> tuple[str, str]:
    container, _, name = path.partition("/")
    if not name:
        raise ValueError(f"Ruta sin contenedor: {path}")
    return container, name


class BlobAudioStorage:
    def __init__(self, endpoint: str, credential: TokenCredential) -> None:
        self._service = BlobServiceClient(endpoint, credential=credential)
        self._key: UserDelegationKey | None = None
        self._key_expiry = datetime.min.replace(tzinfo=UTC)
        self._lock = threading.Lock()

    def save(self, path: str, data: bytes, content_type: str) -> None:
        container, name = _split(path)
        self._service.get_blob_client(container, name).upload_blob(
            data, overwrite=True, content_settings=ContentSettings(content_type=content_type)
        )

    def read(self, path: str) -> bytes:
        container, name = _split(path)
        return self._service.get_blob_client(container, name).download_blob().readall()

    def _delegation_key(self, now: datetime) -> UserDelegationKey:
        with self._lock:
            if self._key is None or now + timedelta(minutes=30) > self._key_expiry:
                self._key_expiry = now + _KEY_LIFETIME
                self._key = self._service.get_user_delegation_key(
                    now - timedelta(minutes=5), self._key_expiry
                )
            return self._key

    def signed_url(self, path: str, ttl: timedelta) -> str:
        container, name = _split(path)
        now = datetime.now(UTC)
        sas = generate_blob_sas(
            account_name=self._service.account_name or "",
            container_name=container,
            blob_name=name,
            user_delegation_key=self._delegation_key(now),
            permission=BlobSasPermissions(read=True),
            start=now - timedelta(minutes=5),
            expiry=now + ttl,
        )
        return f"{self._service.get_blob_client(container, name).url}?{sas}"

    def delete(self, path: str) -> None:
        container, name = _split(path)
        self._service.get_blob_client(container, name).delete_blob()

    def delete_prefix(self, prefix: str) -> None:
        container, name_prefix = _split(prefix)
        client = self._service.get_container_client(container)
        for blob in client.list_blobs(name_starts_with=name_prefix):
            client.delete_blob(blob.name)
