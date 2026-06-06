"""Observer: reacciona a un EVENTO de aplicación (= un Listener de Laravel).

OJO: NO es un Eloquent model-observer — tequio NO ata esto a la BD. El evento se dispara
EXPLÍCITAMENTE con `dispatch(MiEvento(...))` (no por un commit). Subclasea, fija
`observes = MiEvento` y sobreescribe `handle()`. Relación 1:N (varios observers por evento).

Hermano-contraste: el [[Mediator]] enruta UNA intención a UN handler y te DEVUELVE el
resultado (`send`); aquí es notificación 1:N fire-and-forget — no esperas retorno, y el
transporte (síncrono o sobre el broker) lo decide el framework, no tú.

Auto-registro por subclase, mismo patrón que `Seeder` (`Database/Seeder.py`).
"""

from __future__ import annotations

from typing import ClassVar

# Registro de subclases de Observer (se llena al importarlas). Mismo patrón que _SEEDERS.
_OBSERVERS: list[type[Observer]] = []


class Observer:
    """Base de un observer. Cada subclase se auto-registra al definirse."""

    # Tipo de evento que observa; None = todos. Match por tipo EXACTO (sin herencia), KISS.
    observes: ClassVar[type | None] = None

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        _OBSERVERS.append(cls)

    def handle(self, event: object) -> None:
        """Reacciona al evento. Sobreescríbelo en tu subclase (por defecto no hace nada)."""


def registered_observers() -> list[type[Observer]]:
    """Las subclases de Observer registradas (para `dispatch` y tests)."""
    return list(_OBSERVERS)


def reset_observers() -> None:
    """Limpia el registro (SOLO para tests). Espejo de reset_seeders()."""
    _OBSERVERS.clear()
