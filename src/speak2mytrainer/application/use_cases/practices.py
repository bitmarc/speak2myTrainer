"""Prácticas e historial: crear, consultar y borrar, y el audio de la versión mejorada."""

from __future__ import annotations

from uuid import uuid4

from speak2mytrainer.application.ports import (
    AudioStorage,
    PracticeRepository,
    SpeechSynthesizer,
)
from speak2mytrainer.domain.errors import NotFoundError
from speak2mytrainer.domain.models import Attempt, AttemptStatus, Practice, UserProfile

MAX_TITLE_CHARS = 120
MAX_CONTEXT_CHARS = 2000


def audio_prefix(user_id: str, practice_id: str | None = None) -> str:
    return f"audio/{user_id}/" + (f"{practice_id}/" if practice_id else "")


def tts_prefix(user_id: str, practice_id: str | None = None) -> str:
    return f"tts/{user_id}/" + (f"{practice_id}/" if practice_id else "")


def create_practice(
    practices: PracticeRepository, user_id: str, title: str, context: str | None = None
) -> Practice:
    title = title.strip()
    if not title:
        raise ValueError("La práctica necesita un título.")
    practice = Practice(
        id=uuid4().hex,
        user_id=user_id,
        title=title[:MAX_TITLE_CHARS],
        context=(context or "").strip()[:MAX_CONTEXT_CHARS] or None,
    )
    practices.add_practice(practice)
    return practice


def get_practice(practices: PracticeRepository, user_id: str, practice_id: str) -> Practice:
    practice = practices.get_practice(user_id, practice_id)
    if practice is None:
        raise NotFoundError("La práctica no existe.")
    return practice


def get_attempt(practices: PracticeRepository, user_id: str, attempt_id: str) -> Attempt:
    attempt = practices.get_attempt(user_id, attempt_id)
    if attempt is None:
        raise NotFoundError("El intento no existe.")
    return attempt


def delete_practice(
    practices: PracticeRepository, audio: AudioStorage, user_id: str, practice_id: str
) -> None:
    get_practice(practices, user_id, practice_id)
    practices.delete_practice(user_id, practice_id)
    audio.delete_prefix(audio_prefix(user_id, practice_id))
    audio.delete_prefix(tts_prefix(user_id, practice_id))


def delete_history(practices: PracticeRepository, audio: AudioStorage, user_id: str) -> None:
    """Borra todas las prácticas, intentos y audios del usuario. Su perfil y su cuota quedan."""
    practices.delete_all(user_id)
    audio.delete_prefix(audio_prefix(user_id))
    audio.delete_prefix(tts_prefix(user_id))


def tts_path(user: UserProfile, attempt: Attempt) -> str:
    return f"{tts_prefix(user.id, attempt.practice_id)}{attempt.id}-{user.tts_voice}.mp3"


def improved_audio(
    practices: PracticeRepository,
    audio: AudioStorage,
    synthesizer: SpeechSynthesizer,
    user: UserProfile,
    attempt_id: str,
) -> str:
    """Ruta en Blob del mp3 de la versión mejorada con la voz del usuario (RF-16).

    Se genera la primera vez que alguien lo pide y queda en caché: los caracteres de TTS solo
    se gastan en lo que se escucha. Al cambiar de voz se genera de nuevo con la voz nueva.
    """
    attempt = get_attempt(practices, user.id, attempt_id)
    if attempt.status is not AttemptStatus.DONE or not (
        attempt.analysis and attempt.analysis.improved_version.strip()
    ):
        raise NotFoundError("El intento aún no tiene versión mejorada.")
    path = tts_path(user, attempt)
    if attempt.tts_blob == path:
        return path
    practice = practices.get_practice(user.id, attempt.practice_id)
    language = practice.practice_language if practice else "en"
    data = synthesizer.synthesize(attempt.analysis.improved_version, language, user.tts_voice)
    audio.save(path, data, "audio/mpeg")
    attempt.tts_blob = path
    practices.update_attempt(attempt)
    return path
