"""Tocar `app.Models` auto-importa TODOS los modelos (self-discovery via pkgutil),
así SQLAlchemy resuelve las relaciones declaradas por string sin depender del orden
de imports.

El framework BASE no trae modelos (cada proyecto agrega los suyos en app/Models);
este test verifica que el MECANISMO corre sin error y que los mappers configuran.
Con modelos presentes, si faltara importar uno con relación por string, el
`configure_mappers()` lanzaría InvalidRequestError ("failed to locate a name ...").
"""

from __future__ import annotations

from sqlalchemy.orm import configure_mappers

import tequio.Models  # noqa: F401  (el import dispara el self-discovery del __init__)


def test_models_self_discovery_and_mappers_configure() -> None:
    # Con modelos, una relación por string sin resolver tronaría aquí.
    configure_mappers()
