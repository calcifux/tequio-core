"""Tests del registro de seeders + comando `db seed` (sin BD)."""

from __future__ import annotations

import importlib
from collections.abc import Iterator

import pytest

from tequio.Core.Console import registered_commands, reset_registry
from tequio.Core.Database.Seeder import Seeder, registered_seeders, reset_seeders


@pytest.fixture(autouse=True)
def _clean_seeders() -> Iterator[None]:
    reset_seeders()
    yield
    reset_seeders()


def test_seeder_subclass_auto_registers() -> None:
    class _MySeeder(Seeder):
        def run(self) -> None: ...

    assert _MySeeder in registered_seeders()


def test_reset_clears_registry() -> None:
    class _Tmp(Seeder):
        def run(self) -> None: ...

    assert registered_seeders()
    reset_seeders()
    assert registered_seeders() == []


def test_db_seed_command_is_registered() -> None:
    reset_registry()
    import tequio.Core.Console.Commands.SeedCommands as seed_module

    importlib.reload(seed_module)
    groups = registered_commands()

    assert "db" in groups
    assert any(command.name == "seed" for command in groups["db"])
    reset_registry()
