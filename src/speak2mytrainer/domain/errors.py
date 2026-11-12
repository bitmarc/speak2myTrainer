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
