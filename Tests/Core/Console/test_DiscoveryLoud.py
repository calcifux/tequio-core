"""Faro: el discovery NUNCA traga un error real de import (tenet 'nunca falla en silencio').

Distingue ausencia ESPERADA (la carpeta de convención no existe → saltar) de un import ROTO
dentro del módulo del usuario (un typo / símbolo inexistente → re-lanzar). Sin esto, un bug del
dev haría que su observer/job/handler "no se registre" sin un solo log: el peor anti-patrón.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tequio.Core.Console import import_submodules


@pytest.fixture
def _probe_pkg(tmp_path: Path) -> Iterator[str]:
    """Paquete temporal con una carpeta de convención cuyo __init__ tiene un import ROTO."""
    pkg = tmp_path / "loudprobe"
    (pkg / "Observers").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "Observers" / "__init__.py").write_text("import modulo_inexistente_xyz123\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        yield "loudprobe"
    finally:
        sys.path.remove(str(tmp_path))
        for name in [n for n in sys.modules if n == "loudprobe" or n.startswith("loudprobe.")]:
            del sys.modules[name]


def test_broken_import_inside_module_raises(_probe_pkg: str) -> None:
    """Import roto DENTRO de la carpeta → PROPAGA (faro), no se traga en silencio."""
    with pytest.raises(ModuleNotFoundError):
        import_submodules(f"{_probe_pkg}.Observers")


def test_absent_convention_folder_is_silent(_probe_pkg: str) -> None:
    """Carpeta de convención AUSENTE → ausencia esperada, no truena."""
    import_submodules(f"{_probe_pkg}.Handlers")  # no existe; debe ser no-op silencioso
