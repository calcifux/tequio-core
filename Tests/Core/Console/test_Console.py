"""Tests del auto-registro de commands de CLI (sin BD/red).

Probamos el contrato del decorador `@console_command` y del armado de
sub-apps de Typer SIN tocar el sistema de archivos ni el discovery por
`pkgutil`: definimos funciones locales y les fijamos `__module__` a mano para
simular dónde "viven" (en `app.Modules.<X>...` o en `app.Console.Commands...`),
que es lo único que mira la deducción del grupo. Cada test corre aislado gracias
a una fixture autouse que limpia el registro global antes de empezar.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from typer.testing import CliRunner

from tequio.Core.Console import (
    build_cli_apps,
    console_command,
    registered_commands,
    reset_registry,
)
from tequio.Core.Console.Console import _group_from_module


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    """Aísla cada test: el registro es estado GLOBAL module-level, así que lo
    limpiamos antes (y después, por higiene) para que un test no contamine a
    otro ni deje basura para el resto de la suite.
    """
    reset_registry()
    yield
    reset_registry()


def _make_command(module_path: str) -> Callable[[], None]:
    """Crea una función-handler y le fija `__module__` al path indicado.

    Fijar `__module__` es la forma más limpia de simular en qué paquete vive la
    función: la deducción del grupo solo lee ese atributo, no la ubicación real
    del archivo de test.
    """

    def handler() -> None:
        # Cuerpo vacío: estos tests solo miran el registro, no la ejecución.
        ...

    handler.__module__ = module_path
    return handler


def test_group_is_deduced_from_module_path() -> None:
    """Caso 1: sin `group=`, el grupo se deduce del segmento que sigue a
    `Modules` y queda en minúsculas (`app.Modules.CFDI...` → `cfdi`).
    """
    handler = _make_command("app.Modules.CFDI.Console.Commands.GenerateCommand")
    console_command("generate")(handler)

    registry = registered_commands()
    assert set(registry) == {"cfdi"}
    assert len(registry["cfdi"]) == 1
    command = registry["cfdi"][0]
    assert command.group == "cfdi"
    assert command.name == "generate"
    assert command.func is handler  # la función NO se envuelve: queda intacta


def test_group_helper_lowercases_segment_after_modules() -> None:
    """El helper `_group_from_module` baja a minúsculas el segmento que sigue a
    `Modules` y devuelve None cuando no existe ese segmento (command general).
    """
    assert _group_from_module("app.Modules.CFDI.Console.Commands.X") == "cfdi"
    assert _group_from_module("app.Console.Commands.X") is None


def test_explicit_group_is_used_for_general_command() -> None:
    """Caso 2: un command general (fuera de `app.Modules`) declara `group=`
    explícito y ese valor manda, sin intentar deducir nada del módulo.
    """
    handler = _make_command("app.Console.Commands.TestCommand")
    console_command("test", group="mail")(handler)

    registry = registered_commands()
    assert set(registry) == {"mail"}
    assert registry["mail"][0].group == "mail"
    assert registry["mail"][0].name == "test"


def test_value_error_when_group_cannot_be_deduced_and_not_given() -> None:
    """Caso 3: si el módulo no tiene segmento `Modules` y NO se pasa `group=`,
    el decorador exige el grupo explícito lanzando ValueError.
    """
    handler = _make_command("app.Console.Commands.OrphanCommand")
    with pytest.raises(ValueError, match="no se pudo deducir el grupo"):
        console_command("orphan")(handler)


def test_build_cli_apps_groups_sorts_and_runs_commands() -> None:
    """Caso 4: `build_cli_apps` arma un `(grupo, typer.Typer)` por grupo, en
    orden alfabético, y el command montado realmente corre vía CliRunner.
    """

    # El command de CFDI tiene cuerpo observable (echo) para comprobar que
    # realmente se ejecuta cuando lo invocamos por el sub-app.
    def cfdi_body() -> None:
        import typer

        typer.echo("cfdi-ok")

    cfdi_body.__module__ = "app.Modules.CFDI.Console.Commands.GenerateCommand"
    mail_handler = _make_command("app.Console.Commands.TestMailCommand")

    console_command("generate")(cfdi_body)
    console_command("test", group="mail")(mail_handler)

    apps = list(build_cli_apps())
    groups = [group for group, _ in apps]
    assert groups == ["cfdi", "mail"]  # ordenado alfabéticamente

    cfdi_group, cfdi_app = apps[0]
    assert cfdi_group == "cfdi"

    runner = CliRunner()
    result = runner.invoke(cfdi_app, ["generate"])
    assert result.exit_code == 0
    assert "cfdi-ok" in result.stdout


def test_reset_registry_empties_the_registry() -> None:
    """Caso 5: tras registrar algo, `reset_registry` deja el registro vacío."""
    handler = _make_command("app.Modules.CFDI.Console.Commands.X")
    console_command("generate")(handler)
    assert registered_commands() != {}

    reset_registry()
    assert registered_commands() == {}
