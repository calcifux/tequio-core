"""Tests del command bus (Mediator), sin BD."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tequio.Core.Errors import HandlerNotFoundError
from tequio.Core.Mediator import handles, registered_handlers, reset_handlers, send


@pytest.fixture(autouse=True)
def _clean_handlers() -> Iterator[None]:
    reset_handlers()
    yield
    reset_handlers()


def test_handles_registers_and_send_dispatches() -> None:
    class _Greet:
        def __init__(self, who: str) -> None:
            self.who = who

    @handles(_Greet)
    class _GreetHandler:
        def handle(self, command: _Greet) -> str:
            return f"hola {command.who}"

    assert registered_handlers()[_Greet] is _GreetHandler
    assert send(_Greet("memo")) == "hola memo"


def test_send_without_handler_raises_500() -> None:
    class _Unknown:
        pass

    with pytest.raises(HandlerNotFoundError) as exc_info:
        send(_Unknown())
    assert exc_info.value.status_code == 500
    assert exc_info.value.error_code == "handler_not_found"


def test_reset_clears_registry() -> None:
    class _Cmd:
        pass

    @handles(_Cmd)
    class _Handler:
        def handle(self, command: _Cmd) -> None: ...

    assert registered_handlers()
    reset_handlers()
    assert registered_handlers() == {}
