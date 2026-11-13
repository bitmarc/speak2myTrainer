"""Adaptadores `PracticeRepository` y `UserDirectory` sobre Cosmos DB NoSQL.

Los tres contenedores se particionan por `/userId`: el historial de un usuario se lee de una
sola partición. Los documentos son los modelos de dominio serializados, con `user_id`
renombrado a `userId` (la clave de partición) y sin los metadatos de Cosmos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from azure.core.credentials import TokenCredential
from azure.cosmos import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from speak2mytrainer.domain.models import Attempt, Practice, UserProfile

_PK = "userId"


def _to_doc(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    data.pop("user_id", None)
    return data | {_PK: user_id}


def _from_doc(doc: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in doc.items() if not k.startswith("_")}
    clean["user_id"] = clean.pop(_PK)
    return clean


def _read(container: ContainerProxy, item_id: str, user_id: str) -> dict[str, Any] | None:
    try:
        return container.read_item(item_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        return None


def _delete_where(container: ContainerProxy, user_id: str, where: str, **params: str) -> None:
    query = f"SELECT c.id FROM c WHERE c.{_PK} = @user {where}"
    parameters: list[dict[str, object]] = [{"name": "@user", "value": user_id}]
    parameters += [{"name": f"@{k}", "value": v} for k, v in params.items()]
    for item in list(container.query_items(query, parameters=parameters, partition_key=user_id)):
        container.delete_item(item["id"], partition_key=user_id)


class CosmosStore:
    """Cliente compartido por el repositorio y el directorio de usuarios."""

    def __init__(self, endpoint: str, database: str, credential: TokenCredential) -> None:
        db = CosmosClient(endpoint, credential=credential).get_database_client(database)
        self.users = db.get_container_client("users")
        self.practices = db.get_container_client("practices")
        self.attempts = db.get_container_client("attempts")


class CosmosPracticeRepository:
    def __init__(self, store: CosmosStore) -> None:
        self._practices = store.practices
        self._attempts = store.attempts

    def add_practice(self, practice: Practice) -> None:
        self._practices.create_item(_to_doc(practice.user_id, practice.model_dump(mode="json")))

    def get_practice(self, user_id: str, practice_id: str) -> Practice | None:
        doc = _read(self._practices, practice_id, user_id)
        return Practice.model_validate(_from_doc(doc)) if doc else None

    def list_practices(self, user_id: str) -> list[Practice]:
        docs = self._practices.query_items(
            f"SELECT * FROM c WHERE c.{_PK} = @user ORDER BY c.created_at DESC",
            parameters=[{"name": "@user", "value": user_id}],
            partition_key=user_id,
        )
        return [Practice.model_validate(_from_doc(d)) for d in docs]

    def update_practice(self, practice: Practice) -> None:
        self._practices.upsert_item(_to_doc(practice.user_id, practice.model_dump(mode="json")))

    def delete_practice(self, user_id: str, practice_id: str) -> None:
        _delete_where(
            self._attempts, user_id, "AND c.practice_id = @practice", practice=practice_id
        )
        _delete_where(self._practices, user_id, "AND c.id = @practice", practice=practice_id)

    def add_attempt(self, attempt: Attempt) -> None:
        self._attempts.create_item(_to_doc(attempt.user_id, attempt.model_dump(mode="json")))

    def get_attempt(self, user_id: str, attempt_id: str) -> Attempt | None:
        doc = _read(self._attempts, attempt_id, user_id)
        return Attempt.model_validate(_from_doc(doc)) if doc else None

    def list_attempts(self, user_id: str, practice_id: str) -> list[Attempt]:
        docs = self._attempts.query_items(
            f"SELECT * FROM c WHERE c.{_PK} = @user AND c.practice_id = @practice "
            "ORDER BY c.number",
            parameters=[
                {"name": "@user", "value": user_id},
                {"name": "@practice", "value": practice_id},
            ],
            partition_key=user_id,
        )
        return [Attempt.model_validate(_from_doc(d)) for d in docs]

    def update_attempt(self, attempt: Attempt) -> None:
        self._attempts.upsert_item(_to_doc(attempt.user_id, attempt.model_dump(mode="json")))

    def delete_all(self, user_id: str) -> None:
        _delete_where(self._attempts, user_id, "")
        _delete_where(self._practices, user_id, "")

    def monthly_costs(self, since: datetime) -> dict[str, float]:
        # Entre particiones a propósito: es la vista del admin y el volumen es bajo. Las fechas
        # se guardan en ISO 8601 UTC, así que comparar texto ordena igual que comparar fechas.
        docs = self._attempts.query_items(
            f"SELECT c.{_PK}, c.cost_estimate_usd FROM c "
            "WHERE c.created_at >= @since AND IS_NUMBER(c.cost_estimate_usd)",
            parameters=[{"name": "@since", "value": since.strftime("%Y-%m-%dT%H:%M:%S")}],
            enable_cross_partition_query=True,
        )
        costs: dict[str, float] = {}
        for doc in docs:
            costs[doc[_PK]] = costs.get(doc[_PK], 0.0) + doc["cost_estimate_usd"]
        return costs


class CosmosUserDirectory:
    def __init__(self, store: CosmosStore) -> None:
        self._users = store.users

    def get(self, user_id: str) -> UserProfile | None:
        doc = _read(self._users, user_id, user_id)
        if doc is None:
            return None
        doc.pop(_PK, None)
        return UserProfile.model_validate({k: v for k, v in doc.items() if not k.startswith("_")})

    def save(self, user: UserProfile) -> None:
        self._users.upsert_item(user.model_dump(mode="json") | {_PK: user.id})

    def list_users(self) -> list[UserProfile]:
        docs = self._users.query_items("SELECT * FROM c", enable_cross_partition_query=True)
        return [
            UserProfile.model_validate(
                {k: v for k, v in d.items() if not k.startswith("_") and k != _PK}
            )
            for d in docs
        ]
