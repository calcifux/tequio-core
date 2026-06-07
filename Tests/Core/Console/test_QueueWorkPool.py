"""Tests de la opción `--pool` del command `queue work` (selección del pool de Celery).

DB-free y SIN arrancar Celery: monkeypatcheamos `worker_main` del celery_app para CAPTURAR el argv
con que se invocaría, sin levantar proceso. Contrato:
  - `--pool solo`               → argv incluye ["--pool", "solo"] (lo pasa tal cual).
  - sin `--pool` en win32       → AUTO "solo" (el prefork de billiard no es confiable en Windows).
  - sin `--pool` en darwin/linux → argv SIN "--pool" (deja el default de Celery: prefork).

`sys.platform` se monkeypatchea para simular Windows sin correr en Windows. El registro de Console
es estado GLOBAL: se aísla y se re-registra el command en cada test (igual que test_LauncherCommands).
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest
import typer
from pytest import MonkeyPatch
from typer.testing import CliRunner

import tequio.Core.Console.Commands.QueueWorkCommand as queue_module
from tequio.Core.CeleryApp import celery_app
from tequio.Core.Config import settings
from tequio.Core.Console import build_cli_apps, reset_registry


@pytest.fixture(autouse=True)
def _registered_queue() -> Iterator[None]:
    """Aísla el registro y re-registra `queue work` sobre un registro limpio en cada test."""
    reset_registry()
    importlib.reload(queue_module)
    yield
    reset_registry()


def _queue_app() -> typer.Typer:
    """Sub-app de Typer del grupo 'queue', armado desde el registro."""
    apps = {group: sub_app for group, sub_app in build_cli_apps()}
    return apps["queue"]


def _capture_worker_main(monkeypatch: MonkeyPatch) -> dict[str, Any]:
    """Monkeypatchea `worker_main` para capturar el argv sin arrancar el worker."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(celery_app, "worker_main", lambda argv=None: captured.update(argv=argv))
    return captured


def test_explicit_pool_is_passed_through(monkeypatch: MonkeyPatch) -> None:
    """`--pool solo` → argv lleva ["--pool", "solo"] tal cual (sin importar la plataforma)."""
    captured = _capture_worker_main(monkeypatch)

    result = CliRunner().invoke(_queue_app(), ["work", "--pool", "solo"])

    assert result.exit_code == 0
    argv = captured["argv"]
    assert argv[:3] == ["worker", "--loglevel", settings.log_level]
    assert "--pool" in argv and argv[argv.index("--pool") + 1] == "solo"


def test_windows_defaults_pool_to_solo(monkeypatch: MonkeyPatch) -> None:
    """Sin `--pool` en Windows → AUTO 'solo' (el prefork de billiard no es confiable ahí)."""
    monkeypatch.setattr(sys, "platform", "win32")
    captured = _capture_worker_main(monkeypatch)

    result = CliRunner().invoke(_queue_app(), ["work"])

    assert result.exit_code == 0
    argv = captured["argv"]
    assert "--pool" in argv and argv[argv.index("--pool") + 1] == "solo"


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_non_windows_omits_pool_by_default(monkeypatch: MonkeyPatch, platform: str) -> None:
    """Sin `--pool` en darwin/linux → argv SIN '--pool' (se deja el prefork default de Celery)."""
    monkeypatch.setattr(sys, "platform", platform)
    captured = _capture_worker_main(monkeypatch)

    result = CliRunner().invoke(_queue_app(), ["work"])

    assert result.exit_code == 0
    assert "--pool" not in captured["argv"]


def test_queue_list_passes_through_without_namespace(monkeypatch: MonkeyPatch) -> None:
    """Sin QUEUE_NAMESPACE, `--queue emails,celery` llega a -Q tal cual — retrocompatible."""
    monkeypatch.setattr(settings, "queue_namespace", "")
    captured = _capture_worker_main(monkeypatch)

    result = CliRunner().invoke(_queue_app(), ["work", "--queue", "emails,celery"])

    assert result.exit_code == 0
    argv = captured["argv"]
    assert argv[argv.index("-Q") + 1] == "emails,celery"


def test_queue_list_is_qualified_per_name_with_namespace(monkeypatch: MonkeyPatch) -> None:
    """Con QUEUE_NAMESPACE se prefija CADA nombre de la lista (el dev sigue tecleando
    'emails,celery'); se preserva el split por coma y el orden -> 'miapp.emails,miapp.celery'."""
    monkeypatch.setattr(settings, "queue_namespace", "miapp")
    captured = _capture_worker_main(monkeypatch)

    result = CliRunner().invoke(_queue_app(), ["work", "--queue", "emails,celery"])

    assert result.exit_code == 0
    argv = captured["argv"]
    assert argv[argv.index("-Q") + 1] == "miapp.emails,miapp.celery"


def test_queue_omitted_is_not_passed(monkeypatch: MonkeyPatch) -> None:
    """Sin `--queue` (None) no se agrega -Q ni con namespace: el worker consume la cola por
    defecto (que con ns la fija task_default_queue)."""
    monkeypatch.setattr(settings, "queue_namespace", "miapp")
    captured = _capture_worker_main(monkeypatch)

    result = CliRunner().invoke(_queue_app(), ["work"])

    assert result.exit_code == 0
    assert "-Q" not in captured["argv"]
