"""Errores de dominio del framework (neutrales al transporte). Impórtalos desde aquí:

from tequio.Core.Errors import DomainError, ResourceNotFoundError
"""

from __future__ import annotations

from tequio.Core.Errors.Errors import (
    ConflictError,
    DomainError,
    HandlerNotFoundError,
    InvalidFilterError,
    ResourceNotFoundError,
)

__all__ = [
    "ConflictError",
    "DomainError",
    "HandlerNotFoundError",
    "InvalidFilterError",
    "ResourceNotFoundError",
]
