"""Test del borde de error del CLI: un `DomainError` sale como mensaje LIMPIO (mensaje + código),
SIN traceback — simétrico al handler HTTP RFC 9457. Sin esto, Typer escupía el traceback crudo
(con locals) en consola ante un error esperado."""

from __future__ import annotations

from pytest import CaptureFixture

from tequio.Core.Console.Cli import _render_cli_error
from tequio.Core.Errors import ConflictError


def test_domain_error_renders_clean_without_traceback(capsys: CaptureFixture[str]) -> None:
    code = _render_cli_error(ConflictError("Conflicto en esta acción."))

    assert code == 1
    out = capsys.readouterr().out
    assert "Conflicto en esta acción." in out  # el mensaje del dominio, legible
    assert "conflict" in out  # el código estable, como pista
    assert "Traceback" not in out  # NADA de traceback para un error esperado
