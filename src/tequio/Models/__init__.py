"""Modelos COMPARTIDOS (un modelo por archivo, estilo Eloquent app/Models).

Mapean las tablas de la BD y los comparten los módulos que las necesiten
(usuarios, pedidos, catálogos…). Compartirlos evita mapear la misma tabla dos veces.

Auto-import: este __init__ escanea e importa TODOS los modelos de la carpeta al
cargarse (pkgutil), para que SQLAlchemy resuelva las relaciones declaradas por
string (p. ej. Company → CompanyAddress) sin depender del orden de imports. Por
eso `from tequio.Models.Invoice import Invoice` basta: al tocar el paquete se
registran todos. Agregar un modelo = crear su archivo; este __init__ no se toca.
"""

from __future__ import annotations

import importlib
import pkgutil

# Self-discovery: importa cada submódulo de modelos (no los '_') para registrarlos
# en el mapper de SQLAlchemy. Cero lista manual.
for _module_info in pkgutil.iter_modules(__path__):
    if not _module_info.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_module_info.name}")
