"""Instancia de Faker con el locale CONFIGURADO (`FAKER_LOCALE` en .env; default es_MX).

`faker` es dependencia de DEV (factories/seeders/tests), NO del runtime de producción.
OJO: el discovery recursivo del CLI (libertad de encarpetado) importa TODO el árbol de los
módulos — incluidas las factories — así que este módulo SÍ se importa en runtime (p. ej. un
`tequio list` recién instalado de PyPI, sin dev-deps). Por eso el Faker real se carga
PEREZOSO: importar este módulo es gratis; el error accionable sale solo al USARLO.

(Bug real cazado por el smoke del CI 2026-06-06: el import en duro de `faker` tronaba
`tequio list` en una instalación limpia del wheel.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tequio.Core.Config import settings

if TYPE_CHECKING:
    from faker import Faker

_FAKER_MISSING = (
    "Faker no está instalado y las factories/seeders lo necesitan. Es dependencia de "
    "DESARROLLO (no de producción): instálalo con `uv add faker` (ya viene en el dev-group "
    "del proyecto scaffoldeado, así que normalmente basta `uv sync`)."
)


def make_faker() -> Faker:
    """Una instancia nueva de Faker con el locale de `FAKER_LOCALE` (p. ej. es_MX / en_US)."""
    try:
        from faker import Faker
    except ImportError as error:  # pista accionable, no el ModuleNotFoundError pelón
        raise ModuleNotFoundError(_FAKER_MISSING) from error
    return Faker(settings.faker_locale)


class _LazyFaker:
    """Proxy perezoso del Faker compartido: el real se construye en el PRIMER uso
    (`faker.name()`, `faker.sentence()`, ...), no al importar. Así las factories pueden
    importarse en cualquier runtime sin arrastrar la dependencia de dev."""

    def __init__(self) -> None:
        self._real: Faker | None = None

    def __getattr__(self, name: str) -> Any:
        # __getattr__ solo corre para atributos NO encontrados (los métodos de Faker);
        # `_real` sí existe en la instancia, así que no se intercepta a sí mismo.
        if self._real is None:
            self._real = make_faker()
        return getattr(self._real, name)


# Instancia compartida lista para usar en las factories/seeders (perezosa).
faker = _LazyFaker()
