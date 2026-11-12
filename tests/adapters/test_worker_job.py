from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from speak2mytrainer.adapters.inbound import worker_job
from speak2mytrainer.adapters.outbound import fakes
from speak2mytrainer.adapters.outbound.storage_queue import encode_job
from speak2mytrainer.application.container import Container
from speak2mytrainer.application.ports import Transcript
from speak2mytrainer.application.use_cases.practices import create_practice
from speak2mytrainer.bootstrap import Environment, Settings, build_container
from speak2mytrainer.domain.models import Attempt, AttemptStatus, UserProfile

USER = "ana@x.com"


@dataclass
class Message:
    content: str
    dequeue_count: int = 0


@dataclass
class FakeQueueClient:
    """Imita lo que el worker usa de QueueClient: recibir, borrar y reprogramar."""

    messages: list[Message] = field(default_factory=list)
    deleted: list[Message] = field(default_factory=list)
    delayed: list[Message] = field(default_factory=list)

    def receive_message(self, *, visibility_timeout: int) -> Message | None:
        if not self.messages:
            return None
        message = self.messages.pop(0)
        message.dequeue_count += 1
        return message

    def delete_message(self, message: Message) -> None:
        self.deleted.append(message)

    def update_message(self, message: Message, *, visibility_timeout: int) -> None:
        self.delayed.append(message)
        self.messages.append(message)


class BrokenTranscriber:
    def transcribe(self, wav_path: Path, language: str) -> Transcript:
        raise ConnectionError("timeout")


@pytest.fixture
def container(tmp_path: Path) -> Container:
    c = build_container(Settings(env=Environment.CI, local_data_dir=tmp_path))
    c.users.save(UserProfile(id=USER, name="Ana"))
    return c


def submit(container: Container) -> tuple[FakeQueueClient, Attempt]:
    practice = create_practice(container.practices, USER, "Entrevista")
    attempt = container.submit_attempt(USER, practice.id, b"audio", "a.wav")
    assert isinstance(container.queue, fakes.InMemoryJobQueue)
    source = FakeQueueClient([Message(encode_job(j)) for j in container.queue.jobs])
    return source, attempt


def status(container: Container, attempt: Attempt) -> AttemptStatus:
    stored = container.practices.get_attempt(USER, attempt.id)
    assert stored is not None
    return stored.status


def test_run_processes_and_deletes_messages(container: Container) -> None:
    source, attempt = submit(container)

    assert worker_job.run(container, source) == 1  # type: ignore[arg-type]

    assert status(container, attempt) is AttemptStatus.DONE
    assert len(source.deleted) == 1
    assert source.messages == []


def test_first_failure_is_retried_then_marked_failed(container: Container) -> None:
    source, attempt = submit(container)
    broken = replace(container, transcriber=BrokenTranscriber())

    worker_job.process_next(broken, source)  # type: ignore[arg-type]
    assert status(container, attempt) is AttemptStatus.FAILED
    assert len(source.delayed) == 1  # vuelve a la cola para el reintento
    assert source.deleted == []

    worker_job.process_next(broken, source)  # type: ignore[arg-type]
    assert status(container, attempt) is AttemptStatus.FAILED
    assert len(source.deleted) == 1  # segunda entrega: definitivo
    user = container.users.get(USER)
    assert user is not None
    assert user.quota.used_this_month == 0.0  # cuota devuelta


def test_retry_can_succeed(container: Container) -> None:
    source, attempt = submit(container)
    worker_job.process_next(replace(container, transcriber=BrokenTranscriber()), source)  # type: ignore[arg-type]

    worker_job.process_next(container, source)  # type: ignore[arg-type]
    assert status(container, attempt) is AttemptStatus.DONE


def test_message_delivered_too_many_times_is_abandoned(container: Container) -> None:
    source, attempt = submit(container)
    source.messages[0].dequeue_count = 2  # el job murió dos veces sin marcar nada

    worker_job.process_next(container, source)  # type: ignore[arg-type]

    assert status(container, attempt) is AttemptStatus.FAILED
    assert len(source.deleted) == 1
