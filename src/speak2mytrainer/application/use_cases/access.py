"""Acceso: lista blanca, rol admin, cuotas y preferencias."""

from __future__ import annotations

from datetime import datetime

from speak2mytrainer.application.ports import PracticeRepository, UserDirectory
from speak2mytrainer.domain.errors import NotAllowedError, NotFoundError
from speak2mytrainer.domain.models import Quota, Role, UserProfile, VoiceGender

FEEDBACK_LANGUAGES = {"es": "Español", "en": "English"}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def resolve_user(
    users: UserDirectory, email: str, name: str | None, admin_email: str | None
) -> UserProfile:
    """Usuario de la sesión. El admin configurado se da de alta en su primer login y siempre
    conserva el rol y el acceso, aunque su perfil se haya creado antes como usuario normal."""
    email = normalize_email(email)
    user = users.get(email)
    is_admin = admin_email is not None and email == normalize_email(admin_email)
    if is_admin and (user is None or user.role is not Role.ADMIN or not user.allowed):
        user = user or UserProfile(id=email, name=name or email)
        user.role, user.allowed = Role.ADMIN, True
        users.save(user)
    if user is None or not user.allowed:
        raise NotAllowedError(f"{email} no está en la lista de usuarios permitidos.")
    return user


def set_feedback_language(users: UserDirectory, user_id: str, language: str) -> UserProfile:
    if language not in FEEDBACK_LANGUAGES:
        raise ValueError(f"Idioma no admitido: {language}")
    user = _get(users, user_id)
    user.feedback_language = language
    users.save(user)
    return user


def set_tts_voice(users: UserDirectory, user_id: str, voice: VoiceGender) -> UserProfile:
    user = _get(users, user_id)
    user.tts_voice = VoiceGender(voice)
    users.save(user)
    return user


def _get(users: UserDirectory, user_id: str) -> UserProfile:
    user = users.get(user_id)
    if user is None:
        raise NotFoundError(f"No existe el usuario {user_id}.")
    return user


def _require_admin(actor: UserProfile) -> None:
    if actor.role is not Role.ADMIN:
        raise NotAllowedError("Solo el admin puede administrar usuarios.")


def list_users(users: UserDirectory, actor: UserProfile) -> list[UserProfile]:
    _require_admin(actor)
    return sorted(users.list_users(), key=lambda u: u.id)


def allow_user(
    users: UserDirectory, actor: UserProfile, email: str, minutes_per_month: float | None = None
) -> UserProfile:
    """Agrega un correo a la lista blanca o lo reactiva, conservando su historial y su cuota."""
    _require_admin(actor)
    email = normalize_email(email)
    if "@" not in email:
        raise ValueError(f"Correo inválido: {email}")
    user = users.get(email) or UserProfile(id=email, name=email)
    user.allowed = True
    if minutes_per_month is not None:
        user.quota.minutes_per_month = minutes_per_month
    users.save(user)
    return user


def revoke_user(users: UserDirectory, actor: UserProfile, email: str) -> UserProfile:
    _require_admin(actor)
    email = normalize_email(email)
    if email == actor.id:
        raise ValueError("El admin no puede quitarse a sí mismo.")
    user = _get(users, email)
    user.allowed = False
    users.save(user)
    return user


def set_quota(
    users: UserDirectory, actor: UserProfile, email: str, minutes_per_month: float
) -> Quota:
    _require_admin(actor)
    if minutes_per_month < 0:
        raise ValueError("La cuota no puede ser negativa.")
    user = _get(users, normalize_email(email))
    user.quota.minutes_per_month = minutes_per_month
    users.save(user)
    return user.quota


def monthly_spend(
    practices: PracticeRepository, actor: UserProfile, now: datetime
) -> dict[str, float]:
    """Costo estimado del mes calendario (UTC) por usuario, para el panel de admin."""
    _require_admin(actor)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {user: round(usd, 4) for user, usd in practices.monthly_costs(month_start).items()}
