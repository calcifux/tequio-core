"""Tests del shim perezoso de Faker (regresión del smoke del CI, 2026-06-06).

El discovery recursivo del CLI importa TODO el árbol de los módulos (libertad de
encarpetado), incluidas las factories del Demo. En una instalación LIMPIA del wheel
(sin dev-deps) eso tronaba `tequio list`: el shim importaba `faker` EN DURO al
importarse. Cada test corre en SUBPROCESO bloqueando `faker` antes de importar
(simula el wheel sin dev-deps): importar debe ser gratis; el error accionable sale
solo al USAR el faker.
"""

from __future__ import annotations

import subprocess
import sys

# Bloquea `import faker` (None en sys.modules => ImportError), como si no estuviera instalado.
_BLOQUEA_FAKER = "import sys; sys.modules['faker'] = None; "


def test_importing_factories_without_faker_is_free() -> None:
    """Importar las factories (lo que hace `tequio list` vía discovery) NO requiere faker."""
    code = _BLOQUEA_FAKER + "import tequio.Modules.Demo.Factories.factories; print('libre')"

    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert "libre" in result.stdout


def test_using_faker_without_dependency_raises_the_actionable_error() -> None:
    """USARLO sin la dependencia sí truena — con la pista accionable, no el error pelón."""
    code = _BLOQUEA_FAKER + "from tequio.Core.Database.Faker import faker; faker.name()"

    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode != 0
    assert "uv add faker" in result.stderr  # la instrucción, no solo "No module named"
