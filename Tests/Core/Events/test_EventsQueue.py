"""Tests de EVENTS_QUEUE: focalización opcional de la cola de eventos/observers.

Sin redis ni worker: se captura `apply_async` (igual que la suite de Mail) para leer a qué
cola se rutea `events.handle`. El default (vacío) = None => cae en task_default_queue
({ns}.celery), comportamiento de siempre. Con valor => su cola propia, namespaceada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pytest import MonkeyPatch

import tequio.Core.Events.Tasks as events_tasks
from tequio.Core.Config import settings
from tequio.Core.Events import Observer


@dataclass
class _Frase:
    texto: str


class _Obs(Observer):
    observes = _Frase

    def handle(self, event: object) -> None: ...


def _capture_apply_async(monkeypatch: MonkeyPatch) -> dict[str, Any]:
    """Sustituye apply_async por un captor (no toca redis; broker_guard no ve error)."""
    captured: dict[str, Any] = {}

    def _capture(*args: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(events_tasks._handle_event_task, "apply_async", _capture)
    return captured


def test_events_default_queue_is_none_when_unset(monkeypatch: MonkeyPatch) -> None:
    """EVENTS_QUEUE vacío (default): queue=None -> cae en task_default_queue. Retrocompatible."""
    monkeypatch.setattr(settings, "events_queue", "")
    monkeypatch.setattr(settings, "queue_namespace", "")
    captured = _capture_apply_async(monkeypatch)

    events_tasks.enqueue_observer(_Obs, _Frase("hola"))

    assert captured["queue"] is None


def test_events_routed_to_own_queue_when_set(monkeypatch: MonkeyPatch) -> None:
    """EVENTS_QUEUE=events: los eventos van a su cola propia (sin namespace, 'events')."""
    monkeypatch.setattr(settings, "events_queue", "events")
    monkeypatch.setattr(settings, "queue_namespace", "")
    captured = _capture_apply_async(monkeypatch)

    events_tasks.enqueue_observer(_Obs, _Frase("hola"))

    assert captured["queue"] == "events"


def test_events_queue_is_namespaced(monkeypatch: MonkeyPatch) -> None:
    """EVENTS_QUEUE + QUEUE_NAMESPACE: la cola de eventos también se prefija -> 'aqua.events'.
    Así dos apps con eventos en el mismo redis no se cruzan los events.handle."""
    monkeypatch.setattr(settings, "events_queue", "events")
    monkeypatch.setattr(settings, "queue_namespace", "aqua")
    captured = _capture_apply_async(monkeypatch)

    events_tasks.enqueue_observer(_Obs, _Frase("hola"))

    assert captured["queue"] == "aqua.events"
