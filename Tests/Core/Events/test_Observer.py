"""Tests del registro de Observers, sin BD."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tequio.Core.Events import Observer, registered_observers, reset_observers


@pytest.fixture(autouse=True)
def _clean_observers() -> Iterator[None]:
    reset_observers()
    yield
    reset_observers()


def test_observer_subclass_auto_registers() -> None:
    class _MyObserver(Observer):
        observes = int

        def handle(self, event: object) -> None: ...

    assert _MyObserver in registered_observers()


def test_reset_clears_registry() -> None:
    class _Tmp(Observer):
        def handle(self, event: object) -> None: ...

    assert registered_observers()
    reset_observers()
    assert registered_observers() == []
