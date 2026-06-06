"""Unit tests del reloj de la app (sin BD). Espeja app/Core/Clock.py."""

from __future__ import annotations

from datetime import datetime

from tequio.Core.Clock import FixedClock, SystemClock


def test_system_clock_returns_naive_local_datetime() -> None:
    moment = SystemClock().now()
    assert isinstance(moment, datetime)
    assert moment.tzinfo is None  # naive (hora local, como guarda Eloquent)


def test_fixed_clock_always_returns_the_same_moment() -> None:
    frozen = datetime(2026, 1, 1, 12, 0, 0)
    clock = FixedClock(frozen)
    assert clock.now() == frozen
    assert clock.now() == frozen  # congelado, no avanza (= Carbon::setTestNow)
