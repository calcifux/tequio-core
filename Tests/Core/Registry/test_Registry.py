"""Tests de `collect_beat_schedule()`: el beat AGENDA los `@cron_task` descubiertos
(convertidos a crontab) Y fusiona los `beat_schedule` de cada `Console/Kernel.py`,
que GANAN en colisión de nombre.

Sin BD ni red. El registro de crons es un global compartido; lo aislamos con
`reset_cron_registry()` (fixture autouse), igual que test_ScheduleRunCommand. Para
el test de precedencia construimos un módulo SINTÉTICO con su `Console/Kernel.py` en
`tmp_path` (mismo patrón que test_FreeLayoutDiscovery) y limpiamos sys.path/sys.modules
y el registro en teardown para no contaminar el resto de la suite.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from celery.schedules import crontab
from pytest import MonkeyPatch

from tequio.Core.Config import settings
from tequio.Core.Cron import cron_task, every_minute, reset_cron_registry, to_crontab
from tequio.Core.Registry import collect_beat_schedule


@pytest.fixture(autouse=True)
def _isolated_cron_registry() -> Iterator[None]:
    """Aísla el registro de crons: arranca y termina limpio, así no se cuelan los
    crons de otros módulos registrados al importar."""
    reset_cron_registry()
    yield
    reset_cron_registry()


def test_collect_beat_schedule_includes_each_cron_task() -> None:
    @cron_task(name="reg.test.a", schedule=every_minute())
    def task_a() -> str:
        return "ran"

    schedule = collect_beat_schedule()

    assert "reg.test.a" in schedule
    # Sin queue -> sin options; entrada nativa de celery beat {task, schedule}.
    assert schedule["reg.test.a"] == {"task": "reg.test.a", "schedule": to_crontab(every_minute())}


def test_cron_task_with_queue_sets_options_queue() -> None:
    @cron_task(name="reg.test.q", schedule=every_minute(), queue="emails")
    def task_q() -> str:
        return "ran"

    entry = collect_beat_schedule()["reg.test.q"]

    # La cola se enruta con options.queue (= el apply_async(queue=...) de schedule run).
    assert isinstance(entry, dict)
    assert entry["options"] == {"queue": "emails"}


def test_cron_task_without_schedule_is_not_in_beat() -> None:
    @cron_task(name="reg.test.noSched")
    def task_no_schedule() -> str:
        return "ran"

    # registered_crons() ya excluye los crons sin cadencia -> no entran al beat.
    assert "reg.test.noSched" not in collect_beat_schedule()


# --------------------------------------------------------- precedencia Kernel.py sobre @cron_task
# Paquete de MÓDULOS sintético (= settings.modules_package). module_packages() escanea sus
# subpaquetes; cada subpaquete es un módulo, y collect_beat_schedule importa su Console/Kernel.
_PKG = "registry_precedence_probe"
_MODULE = "Probe"

# Un módulo sintético con su Console/Kernel.py declarando un beat_schedule que COLISIONA
# (mismo nombre) con un @cron_task auto-derivado. El contrato exige que Kernel.py GANE.
_KERNEL = '''"""Console/Kernel.py sintético: declara un beat_schedule que colisiona a propósito."""

from __future__ import annotations

from celery.schedules import crontab

beat_schedule = {
    "collision.name": {"task": "kernel.version", "schedule": crontab(minute="0")},
}
'''


def _write_kernel_pkg(root: Path) -> None:
    """Crea `<root>/registry_precedence_probe/Probe/Console/Kernel.py` con __init__ en cada nivel."""
    console_dir = root / _PKG / _MODULE / "Console"
    console_dir.mkdir(parents=True)
    for level in (root / _PKG, root / _PKG / _MODULE, console_dir):
        (level / "__init__.py").write_text("", encoding="utf-8")
    (console_dir / "Kernel.py").write_text(_KERNEL, encoding="utf-8")


@pytest.fixture
def _synthetic_kernel(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[str]:
    """Paquete de módulos sintético con Console/Kernel.py + settings.modules_package
    y sys.path apuntados a él. Limpia sys.path/sys.modules en teardown (el registro de
    crons lo limpia la fixture autouse)."""
    _write_kernel_pkg(tmp_path)
    sys.path.insert(0, str(tmp_path))
    monkeypatch.setattr(settings, "modules_package", _PKG)
    try:
        yield _PKG
    finally:
        sys.path.remove(str(tmp_path))
        for name in [n for n in sys.modules if n == _PKG or n.startswith(f"{_PKG}.")]:
            del sys.modules[name]


def test_kernel_beat_schedule_takes_precedence_over_cron_task(_synthetic_kernel: str) -> None:
    # Mismo nombre por las dos vías: el @cron_task auto-derivado y el Kernel.py declarativo.
    @cron_task(name="collision.name", schedule=every_minute())
    def colliding_task() -> str:
        return "ran"

    schedule = collect_beat_schedule()

    # Kernel.py se aplica AL FINAL: su entrada sobrescribe a la auto-derivada.
    entry = schedule["collision.name"]
    assert isinstance(entry, dict)
    assert entry["task"] == "kernel.version"
    assert entry["schedule"] == crontab(minute="0")
