"""Unit tests del decorador cron_task (sin BD ni Redis).
Espeja app/Core/Cron.py. Solo el gate por entorno (no usa lock → no toca Redis).
"""

from __future__ import annotations

import pytest

from tequio.Core.Config import settings
from tequio.Core.Cron import cron_task


def test_cron_task_skips_when_env_not_allowed() -> None:
    calls: list[int] = []

    @cron_task(name="test.cron.skip_env", environments=["__never__"])
    def task() -> str:
        calls.append(1)
        return "ran"

    assert task() is None  # omitida por entorno
    assert calls == []  # la función NO corrió


def test_cron_task_runs_when_env_allowed() -> None:
    calls: list[int] = []

    @cron_task(name="test.cron.run_env", environments=[settings.app_env])
    def task() -> str:
        calls.append(1)
        return "ran"

    assert task() == "ran"
    assert calls == [1]


def test_cron_task_runs_when_no_environments_filter() -> None:
    @cron_task(name="test.cron.no_env")
    def task() -> str:
        return "ran"

    assert task() == "ran"


def test_overlap_lock_must_exceed_broker_visibility_timeout() -> None:
    """Invariante anti-doble-ejecución: con without_overlapping, un lock_timeout
    <= visibility_timeout se rechaza al decorar (si no, un cron largo correría dos
    veces tras la reentrega de Redis)."""
    with pytest.raises(ValueError, match="visibility_timeout"):

        @cron_task(
            name="test.cron.bad_lock",
            without_overlapping=True,
            lock_timeout=settings.redis_visibility_timeout,  # igual = inseguro
        )
        def task() -> str:
            return "ran"
