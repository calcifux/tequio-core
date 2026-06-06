"""Seeders: pueblan la BD con datos iniciales/demo (= los seeders de Laravel).

Subclasea `Seeder` e implementa `run()`. Se descubren en `app/Modules/<X>/Seeders/` y se corren
con `tequio db:seed` (cada uno dentro de su propia transacción). La IDEMPOTENCIA es tu
responsabilidad (revisa si el dato ya existe antes de crearlo), igual que en Laravel.
"""

from __future__ import annotations

# Registro de subclases de Seeder (se llena al importarlas). Mismo patrón que el resto.
_SEEDERS: list[type[Seeder]] = []


class Seeder:
    """Base de un seeder. Cada subclase se auto-registra al definirse."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        _SEEDERS.append(cls)

    def run(self) -> None:
        raise NotImplementedError


def registered_seeders() -> list[type[Seeder]]:
    """Las subclases de Seeder registradas (para `db:seed` y tests)."""
    return list(_SEEDERS)


def reset_seeders() -> None:
    """Limpia el registro (SOLO para tests)."""
    _SEEDERS.clear()
