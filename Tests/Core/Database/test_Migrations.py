"""Tests de la integración con Alembic, SIN tocar BD.

Verifican: (1) la Config apunta a migrations/ correctamente, (2) los commands `migrate`
se registran, y (3) cada command delega en el helper de Alembic con los argumentos
correctos (los helpers se monkeypatchean: no se ejecuta Alembic ni se abre conexión).
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import typer
from pytest import MonkeyPatch
from typer.testing import CliRunner

import tequio.Core.Console.Commands.MigrateCommands as migrate_module
from tequio.Core.Console import build_cli_apps, registered_commands, reset_registry
from tequio.Core.Database.Migrations import make_alembic_config


def test_alembic_config_points_to_migrations_dir() -> None:
    config = make_alembic_config()
    script_location = config.get_main_option("script_location")

    assert script_location is not None
    location = Path(script_location)
    assert location.name == "migrations"
    assert (location / "env.py").is_file()
    assert (location / "versions").is_dir()


@pytest.fixture
def _registered_migrate() -> Iterator[None]:
    """Aísla el registro y re-registra los commands `migrate` sobre un registro limpio."""
    reset_registry()
    importlib.reload(migrate_module)
    yield
    reset_registry()


def _migrate_app() -> typer.Typer:
    apps = {group: sub_app for group, sub_app in build_cli_apps()}
    return apps["migrate"]


def test_migrate_group_registers_all_commands(_registered_migrate: None) -> None:
    groups = registered_commands()

    assert "migrate" in groups
    names = {command.name for command in groups["migrate"]}
    assert names == {"make", "run", "status", "rollback"}


def test_migrate_make_delegates_with_message(_registered_migrate: None, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        migrate_module,
        "make_revision",
        lambda message, autogenerate=True: captured.update(message=message, autogenerate=autogenerate),
    )

    result = CliRunner().invoke(_migrate_app(), ["make", "-m", "crear facturas"])

    assert result.exit_code == 0
    assert captured == {"message": "crear facturas", "autogenerate": True}


def test_migrate_make_requires_message(_registered_migrate: None) -> None:
    result = CliRunner().invoke(_migrate_app(), ["make"])
    assert result.exit_code != 0  # -m/--message es obligatorio


def test_migrate_run_delegates_to_upgrade(_registered_migrate: None, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(migrate_module, "run_upgrade", lambda to: captured.update(to=to))

    result = CliRunner().invoke(_migrate_app(), ["run", "--to", "head"])

    assert result.exit_code == 0
    assert captured == {"to": "head"}
