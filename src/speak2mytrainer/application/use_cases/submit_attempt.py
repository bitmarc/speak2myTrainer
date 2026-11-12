"""Enviar un intento: validar, reservar cuota, guardar el audio y encolar el análisis.

Lo que se descarta con "Reintentar" nunca llega aquí, así que no deja rastro.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from uuid import uuid4

from speak2mytrainer.application.ports import (
    AttemptJob,
    AudioConverter,
    AudioStorage,
    JobQueue,
    PracticeRepository,
    UserDirectory,
)
from speak2mytrainer.application.use_cases.practices import audio_prefix, get_practice
from speak2mytrainer.domain.errors import NotFoundError, QuotaExceededError, UnsupportedAudioError
from speak2mytrainer.domain.metrics import validate_duration
from speak2mytrainer.domain.models import Attempt, utcnow

CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".aac": "audio/aac",
}


@dataclass(frozen=True)
class SubmitAttempt:
    practices: PracticeRepository
    users: UserDirectory
    audio: AudioStorage
    queue: JobQueue
    converter: AudioConverter

    def __call__(self, user_id: str, practice_id: str, data: bytes, filename: str) -> Attempt:
        practice = get_practice(self.practices, user_id, practice_id)
        suffix = PurePath(filename).suffix.lower() or ".wav"
        if suffix not in CONTENT_TYPES:
            raise UnsupportedAudioError(
                f"Formato {suffix} no admitido. Usa {', '.join(sorted(CONTENT_TYPES))}."
            )
        duration = self.converter.duration_sec(data, suffix)
        validate_duration(duration)

        # La cuota se reserva al enviar (no al terminar) para que no se puedan encolar más
        # minutos de los disponibles; si el análisis falla definitivamente, se devuelve.
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError(f"No existe el usuario {user_id}.")
        user.quota.roll_over_if_needed(utcnow())
        if not user.quota.allows(duration):
            raise QuotaExceededError(
                f"Te quedan {user.quota.remaining_minutes():.1f} min este mes y el audio dura "
                f"{duration / 60:.1f} min."
            )

        attempt_id = uuid4().hex
        blob = f"{audio_prefix(user_id, practice_id)}{attempt_id}{suffix}"
        self.audio.save(blob, data, CONTENT_TYPES[suffix])

        attempt = Attempt(
            id=attempt_id,
            user_id=user_id,
            practice_id=practice_id,
            number=practice.attempt_count + 1,
            audio_blob=blob,
            duration_sec=round(duration, 1),
        )
        self.practices.add_attempt(attempt)
        practice.attempt_count = attempt.number
        practice.last_attempt_at = attempt.created_at
        self.practices.update_practice(practice)

        user.quota.consume(duration)
        self.users.save(user)

        self.queue.enqueue(
            AttemptJob(user_id=user_id, practice_id=practice_id, attempt_id=attempt_id)
        )
        return attempt
