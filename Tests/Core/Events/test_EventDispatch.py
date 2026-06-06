"""Tests del dispatch de eventos (transporte adaptativo), sin BD ni broker real.

La rama encolada se monkeypatchea (`enqueue_observer`) para no tocar redis: simular "hay
broker" (no lanza) o "no hay broker" (lanza QueueUnavailableError, que fuerza el fallback
síncrono).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pytest import MonkeyPatch

import tequio.Core.Events.Tasks as events_tasks
from tequio.Core.CeleryApp import QueueUnavailableError
from tequio.Core.Events import Observer, dispatch, reset_observers


class _Created:
    pass


@pytest.fixture(autouse=True)
def _clean_observers() -> Iterator[None]:
    reset_observers()
    yield
    reset_observers()


def _no_broker(observer_cls: type[Observer], event: object) -> None:
    raise QueueUnavailableError("sin broker")


def test_runs_sync_when_broker_unavailable(monkeypatch: MonkeyPatch) -> None:
    ran: list[str] = []

    class _Obs(Observer):
        observes = _Created

        def handle(self, event: object) -> None:
            ran.append("sync")

    monkeypatch.setattr(events_tasks, "enqueue_observer", _no_broker)
    dispatch(_Created())
    assert ran == ["sync"]


def test_enqueues_when_broker_available(monkeypatch: MonkeyPatch) -> None:
    enqueued: list[type[Observer]] = []
    ran: list[str] = []

    class _Obs(Observer):
        observes = _Created

        def handle(self, event: object) -> None:
            ran.append("sync")

    def _ok(observer_cls: type[Observer], event: object) -> None:
        enqueued.append(observer_cls)

    monkeypatch.setattr(events_tasks, "enqueue_observer", _ok)
    dispatch(_Created())
    assert enqueued == [_Obs]  # se encoló sobre el broker
    assert ran == []  # NO corrió síncrono


def test_failing_observer_does_not_propagate(monkeypatch: MonkeyPatch) -> None:
    class _Boom(Observer):
        observes = _Created

        def handle(self, event: object) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(events_tasks, "enqueue_observer", _no_broker)
    dispatch(_Created())  # best-effort: un observer que falla NO debe propagar


def test_observer_only_fires_for_its_event(monkeypatch: MonkeyPatch) -> None:
    ran: list[str] = []

    class _Other:
        pass

    class _Obs(Observer):
        observes = _Created

        def handle(self, event: object) -> None:
            ran.append("fired")

    monkeypatch.setattr(events_tasks, "enqueue_observer", _no_broker)
    dispatch(_Other())
    assert ran == []  # observes=_Created no matchea _Other
