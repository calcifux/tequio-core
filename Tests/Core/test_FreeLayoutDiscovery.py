"""EL test de la LIBERTAD de encarpetado: el discovery importa TODO el árbol de cada módulo, así
que un `@console_command` y un `@job` registran AUNQUE vivan en un archivo ANIDADO con nombre
arbitrario (aquí: `cosecha/maquinaria/trilladora.py`). No hay carpetas de convención obligatorias
(Jobs/, Console/Commands/...): "ya como haga el programador su aplicación, nos vale".

Sin BD ni red. Construimos en `tmp_path` un paquete de módulos SINTÉTICO, apuntamos
`settings.modules_package` y `sys.path` hacia él, y verificamos que tras `import_all_tasks()` /
`iter_cli_apps()` el job y el command quedaron registrados. Limpiamos TODO el estado global
(registros de Console y Cron/Celery, sys.modules, sys.path) para no contaminar el resto de la suite.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from tequio.Core.Config import settings
from tequio.Core.Console import registered_commands, reset_registry
from tequio.Core.Registry import import_all_tasks, iter_cli_apps

# Nombre del paquete de módulos sintético y del grupo del command. El paquete NO contiene el
# segmento "Modules", así que la deducción de grupo no aplica: el @console_command declara `group=`
# explícito (lo mismo que exige el framework para commands fuera de app.Modules).
_PKG = "libertad_layout_probe"
_GROUP = "cosecha"

# El @console_command y el @job viven JUNTOS en un archivo PROFUNDO de nombre arbitrario. El punto
# del test: el discovery los encuentra igual, sin que estén en Jobs/ ni en Console/Commands/.
_NESTED = '''"""Archivo anidado de nombre arbitrario: prueba que el discovery desciende todo el árbol."""

from __future__ import annotations

from tequio.Core.Console import console_command
from tequio.Core.Jobs import job


@job(name="cosecha.trillar")
def trillar(parcela_id: int) -> int:
    return parcela_id


@console_command(name="trillar", group="cosecha", help="Trilla una parcela (vive ANIDADO).")
def trillar_command(parcela_id: int) -> None:
    ...
'''


def _write_pkg(root: Path) -> None:
    """Crea `<root>/libertad_layout_probe/cosecha/maquinaria/trilladora.py` con __init__ en cada nivel."""
    nested_dir = root / _PKG / "cosecha" / "maquinaria"
    nested_dir.mkdir(parents=True)
    for level in (root / _PKG, root / _PKG / "cosecha", nested_dir):
        (level / "__init__.py").write_text("", encoding="utf-8")
    (nested_dir / "trilladora.py").write_text(_NESTED, encoding="utf-8")


@pytest.fixture
def _synthetic_modules(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[str]:
    """Paquete de módulos sintético en disco + settings.modules_package y sys.path apuntados a él.

    Aísla el estado global: limpia el registro de Console antes/después, apunta los settings al
    paquete temporal (monkeypatch los revierte), y purga sys.path / sys.modules en teardown para
    que el job de Celery y el command no se filtren a otros tests.
    """
    reset_registry()
    _write_pkg(tmp_path)
    sys.path.insert(0, str(tmp_path))
    monkeypatch.setattr(settings, "modules_package", _PKG)
    try:
        yield _PKG
    finally:
        sys.path.remove(str(tmp_path))
        for name in [n for n in sys.modules if n == _PKG or n.startswith(f"{_PKG}.")]:
            del sys.modules[name]
        reset_registry()


def test_console_command_in_nested_arbitrary_file_is_discovered(_synthetic_modules: str) -> None:
    """`iter_cli_apps()` importa todo el árbol y arma el sub-app: el command anidado queda registrado."""
    apps = {group: sub_app for group, sub_app in iter_cli_apps()}

    assert _GROUP in apps  # el grupo 'cosecha' se montó desde un archivo anidado de nombre libre
    names = {command.name for command in registered_commands()[_GROUP]}
    assert "trillar" in names


def test_job_in_nested_arbitrary_file_is_discovered(_synthetic_modules: str) -> None:
    """`import_all_tasks()` importa todo el árbol: el @job anidado registra su task de Celery."""
    from tequio.Core.CeleryApp import celery_app

    import_all_tasks()

    assert "cosecha.trillar" in celery_app.tasks  # el decorador @job corrió → task registrada
