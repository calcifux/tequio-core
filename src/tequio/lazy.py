"""Import perezoso (estilo tequio): difiere libs pesadas/opcionales al PRIMER uso.

El auto-discovery importa TODOS los módulos de la app para registrar tasks/observers/rutas
— y con ellos sus `import openpyxl`/`import pandas` al tope, que terminan cargados en procesos
que NO los usan (el worker que nunca genera Excel carga openpyxl igual; el motor de subastas
tipo-tequio cargaría sus libs de Excel en cada proceso). Este helper deja que un módulo
"importe" esas libs SIN pagarlas hasta que de verdad se usen.

    from tequio.lazy import openpyxl          # NO carga openpyxl aún (solo lo nombra)
    ...
    wb = openpyxl.Workbook()                  # se carga AQUÍ, la 1ª vez que se usa

    # submódulos (la API de openpyxl vive en .styles/.utils): forma explícita
    from tequio.lazy import load
    styles = load("openpyxl.styles")
    celda.font = styles.Font(bold=True)

Es OPT-IN y documentado: el dev que lo ignora sigue con `import openpyxl` normal (eager) —
no rompe nada, solo no ahorra. Respaldado por `importlib.util.LazyLoader` (stdlib).

OJO (límite honesto): lazy es del MÓDULO, no de `from openpyxl import Workbook` (esa forma
ACCEDE al atributo y dispara la carga). Y el módulo no se debe ACCEDER en el cuerpo del
módulo (a nivel top-level) — solo dentro de funciones —, o se carga en el discovery igual.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType


def load(name: str) -> ModuleType:
    """Devuelve el módulo `name` en modo PEREZOSO: su código corre al primer acceso de
    atributo, no al importarlo. Soporta submódulos ('openpyxl.styles'). Si ya está cargado,
    lo devuelve tal cual (idempotente)."""
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.find_spec(name)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"tequio.lazy: no se encontró el módulo '{name}'")
    spec.loader = importlib.util.LazyLoader(spec.loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def __getattr__(name: str) -> ModuleType:  # PEP 562
    """`from tequio.lazy import openpyxl` cae aquí -> openpyxl perezoso."""
    # Los dunders (__path__, __all__, ...) NO son libs: deja que Python los maneje normal
    # (sin esto, `from tequio.lazy import X` intenta cargar el módulo '__path__' y truena).
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(name)
    return load(name)
