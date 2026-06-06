"""Tests del Pipeline (modelo cebolla), puro y sin BD."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tequio.Core.Pipeline import Pipeline


class _Append:
    """Pipe que agrega un token y sigue (llama next)."""

    def __init__(self, token: str) -> None:
        self._token = token

    def handle(self, passable: Any, next: Callable[[Any], Any]) -> Any:  # noqa: A002 — calca a Laravel
        passable.append(self._token)
        return next(passable)


class _Stop:
    """Pipe que CORTA el flujo: no llama next."""

    def handle(self, passable: Any, next: Callable[[Any], Any]) -> Any:  # noqa: A002
        return "cortado"


def test_pipes_run_in_order() -> None:
    result = Pipeline().send([]).through([_Append("a"), _Append("b")]).then_return()
    assert result == ["a", "b"]


def test_then_calls_destination_at_the_core() -> None:
    result = Pipeline().send([]).through([_Append("x")]).then(lambda items: ",".join(items))
    assert result == "x"


def test_pipe_can_short_circuit() -> None:
    seen: list[str] = []
    result = Pipeline().send(seen).through([_Append("a"), _Stop(), _Append("never")]).then_return()
    assert result == "cortado"
    assert seen == ["a"]  # la etapa posterior al corte NO corrió
