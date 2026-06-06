"""Localiza en disco la carpeta de un paquete (importable o pip-instalado) SIN
ejecutarlo, para descubrir recursos por-módulo (vistas, lang, static) sin recurrir
a aritmética de `__file__`/`parents[N]`.

Por qué existe: cuando tequio se instala como paquete, `Path(__file__).parents[N]`
apunta a site-packages, no al proyecto del usuario. `find_spec` resuelve la ruta REAL
del paquete configurado (p. ej. `settings.modules_package`), funcione en el repo o
instalado. Es la pieza que vuelve a tequio "consciente" de dónde vive el código del
usuario en vez de adivinarlo contando carpetas.

Aquí vive además `_module_absent`: el criterio que el discovery usa para distinguir una
AUSENCIA esperada (la carpeta de convención no existe → saltar) de un import ROTO dentro
del módulo del usuario (bug real → re-lanzar, nunca silenciar). Ver tenet "nunca falla en silencio".
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _module_absent(error: ModuleNotFoundError, target: str) -> bool:
    """True si el `ModuleNotFoundError` es por AUSENCIA del paquete `target` (o un ancestro
    suyo) — ausencia ESPERADA, el discovery puede saltarla. False si el import que falló viene
    de DENTRO del módulo (un typo / símbolo inexistente) — es un BUG REAL y hay que re-lanzarlo:
    silenciar eso haría que tu observer/job/handler "no se registre" sin un solo log."""
    name = error.name
    return name is not None and (target == name or target.startswith(f"{name}."))


def package_dir(dotted: str) -> Path | None:
    """Carpeta en disco del paquete `dotted` (p. ej. "app.Modules"), o None si no
    existe o no es un paquete. No ejecuta el `__init__` del paquete (usa find_spec).

    Faro: si el paquete (o un ancestro) simplemente no existe → None (ausencia esperada);
    pero si resolver el spec falla por un import ROTO, se re-lanza (no se traga el bug).
    """
    try:
        spec = importlib.util.find_spec(dotted)
    except ModuleNotFoundError as error:
        if _module_absent(error, dotted):
            return None
        raise
    except ValueError:
        # find_spec lanza ValueError para módulos sin __spec__ (p. ej. __main__): no es
        # un paquete con carpeta en disco → None (benigno, no es un error a propagar).
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(next(iter(spec.submodule_search_locations)))
