"""Test del render `php artisan list` (format_command_list)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tequio.Core.Console import build_command_table, console_command, format_command_list, reset_registry


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    reset_registry()
    yield
    reset_registry()


def _make_command(module_path: str):  # type: ignore[no-untyped-def]
    def handler() -> None: ...

    handler.__module__ = module_path
    return handler


def test_lists_every_group_and_command_with_help() -> None:
    console_command("generate", group="cfdi", help="Genera CFDI.")(_make_command("app.Modules.CFDI.X"))
    console_command("test", group="mail", help="Smoke de correo.")(_make_command("app.Console.Commands.X"))

    output = format_command_list()

    # Aparecen los grupos y los commands con su invocación completa y su ayuda.
    assert "cfdi" in output
    assert "cfdi generate" in output
    assert "Genera CFDI." in output
    assert "mail test" in output
    assert "Smoke de correo." in output
    # Grupos ordenados alfabéticamente: cfdi antes que mail.
    assert output.index("cfdi") < output.index("mail test")


def test_build_command_table_has_columns_and_one_row_per_command() -> None:
    console_command("generate", group="cfdi", help="Genera CFDI.")(_make_command("app.Modules.CFDI.X"))
    console_command("test", group="mail", help="Smoke de correo.")(_make_command("app.Console.Commands.X"))

    table = build_command_table()

    assert table.columns[0].header == "Comando"
    assert table.columns[1].header == "Descripción"
    assert table.row_count == 2  # una fila por command
