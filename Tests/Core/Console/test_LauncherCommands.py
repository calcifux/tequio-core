"""Tests de los commands launcher del framework (`queue work`, `schedule work`).

DB-free y SIN arrancar Celery de verdad: monkeypatcheamos `worker_main`/`start`
del celery_app para capturar con qué argumentos se invocaría, sin levantar ningún
proceso. Fakes y monkeypatch, cero BD/red.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any

import pytest
import typer
from pytest import MonkeyPatch
from typer.testing import CliRunner

import tequio.Core.Console.Commands.QueueWorkCommand as queue_module
import tequio.Core.Console.Commands.ScheduleWorkCommand as schedule_module
from tequio.Core.CeleryApp import celery_app
from tequio.Core.Config import settings
from tequio.Core.Console import build_cli_apps, reset_registry


@pytest.fixture(autouse=True)
def _registered_launchers() -> Iterator[None]:
    """Aísla el registro y re-registra los launchers en cada test: el reset borra
    lo que el import dejó, así que recargamos los módulos para re-disparar sus
    `@console_command` sobre el registro limpio."""
    reset_registry()
    importlib.reload(queue_module)
    importlib.reload(schedule_module)
    yield
    reset_registry()


def _apps() -> dict[str, typer.Typer]:
    """Sub-apps de Typer por grupo, armados desde el registro."""
    return {group: sub_app for group, sub_app in build_cli_apps()}


def test_queue_work_launches_worker_without_embedded_beat(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(celery_app, "worker_main", lambda argv=None: captured.update(argv=argv))

    result = CliRunner().invoke(_apps()["queue"], ["work", "--concurrency", "4"])

    assert result.exit_code == 0
    # Arranca el worker, NUNCA con beat embebido (-B): el despertador va aparte.
    assert captured["argv"] == ["worker", "--loglevel", settings.log_level, "--concurrency", "4"]
    assert "-B" not in captured["argv"]


def test_schedule_work_launches_beat(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(celery_app, "start", lambda argv=None: captured.update(argv=argv))

    result = CliRunner().invoke(_apps()["schedule"], ["work"])

    assert result.exit_code == 0
    assert captured["argv"] == ["beat", "--loglevel", settings.log_level]
