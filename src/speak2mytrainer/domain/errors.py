"""Errores del dominio."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from speak2mytrainer.domain.models import AttemptStatus


class DomainError(Exception):
    """Base de los errores de reglas de negocio."""


class InvalidStatusTransitionError(DomainError):
    def __init__(self, current: AttemptStatus, new: AttemptStatus) -> None:
        super().__init__(f"Transición de estado inválida: {current} -> {new}")
        self.current = current
        self.new = new


class AudioDurationError(DomainError):
    """La duración del audio está fuera del rango permitido."""


class QuotaExceededError(DomainError):
    """El usuario agotó sus minutos de audio del mes."""


class NotAllowedError(DomainError):
    """El correo no está en la lista blanca o el usuario no tiene permiso para la acción."""


class NotFoundError(DomainError):
    """La práctica o el intento no existe (o no pertenece al usuario)."""


class UnsupportedAudioError(DomainError):
    """Formato de audio no admitido o archivo que ffmpeg no puede leer."""


class ServiceQuotaError(DomainError):
    """Un servicio externo rechazó la solicitud por cuota, p. ej. las 5 h al mes de Speech F0."""
