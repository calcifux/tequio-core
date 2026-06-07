"""Test de la KEY del lock anti-overlap bajo QUEUE_NAMESPACE.

El lock de `without_overlapping` vive en el LOCK store (redis), independiente del broker.
Con varias apps en el MISMO redis, dos crons HOMÓNIMOS compartirían la key `cron-lock:{name}`
y se bloquearían entre sí. Con QUEUE_NAMESPACE la key se namespacea a `cron-lock:{ns}:{name}`;
sin namespace, la key actual `cron-lock:{name}` queda INTACTA (retrocompatible).

Sin redis real: monkeypatcheamos `_get_redis()` por un cliente fake que CAPTURA la key con
que se pidió `.lock(...)` y devuelve un lock no-op que siempre adquiere.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from pytest import MonkeyPatch

from tequio.Core.Config import settings
from tequio.Core.Cron import Cron as CronModule
from tequio.Core.Cron import cron_task


class _FakeLock:
    """Lock no-op: siempre adquiere y libera sin tocar redis."""

    def acquire(self, *, blocking: bool = False) -> bool:
        return True

    def release(self) -> None:
        return None


class _FakeRedis:
    """Cliente redis fake: registra la key con que se invocó `.lock(...)`."""

    def __init__(self) -> None:
        self.lock_keys: list[str] = []

    def lock(self, key: str, **_kwargs: Any) -> _FakeLock:
        self.lock_keys.append(key)
        return _FakeLock()


@pytest.fixture
def _fake_redis(monkeypatch: MonkeyPatch) -> Iterator[_FakeRedis]:
    fake = _FakeRedis()
    monkeypatch.setattr(CronModule, "_get_redis", lambda: fake)
    yield fake


def test_lock_key_plain_without_namespace(monkeypatch: MonkeyPatch, _fake_redis: _FakeRedis) -> None:
    """Sin namespace: la key es `cron-lock:{name}` (la de siempre, intacta)."""
    monkeypatch.setattr(settings, "queue_namespace", "")

    @cron_task(name="test.cron.lock_plain", without_overlapping=True)
    def task() -> str:
        return "ran"

    assert task() == "ran"
    assert _fake_redis.lock_keys == ["cron-lock:test.cron.lock_plain"]


def test_lock_key_namespaced_with_namespace(monkeypatch: MonkeyPatch, _fake_redis: _FakeRedis) -> None:
    """Con namespace: la key es `cron-lock:{ns}:{name}` — dos apps no comparten el lock
    de un cron homónimo en el mismo redis."""
    monkeypatch.setattr(settings, "queue_namespace", "miapp")

    @cron_task(name="test.cron.lock_ns", without_overlapping=True)
    def task() -> str:
        return "ran"

    assert task() == "ran"
    assert _fake_redis.lock_keys == ["cron-lock:miapp:test.cron.lock_ns"]
