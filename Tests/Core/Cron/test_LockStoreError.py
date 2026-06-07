"""Test del error ACCIONABLE cuando el LOCK store (redis) no conecta.

`without_overlapping` EXIGE el lock store. Si redis no responde, NO caemos al broker ni
lo silenciamos (eso permitiría doble-timbrado sigiloso): se levanta un error accionable que
menciona LOCK_URL y el caso docker. Apuntamos el lock a un puerto MUERTO y verificamos el
mensaje. blocking=False + connect-on-acquire => el fallo aparece al adquirir (sync, sin worker).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pytest import MonkeyPatch

from tequio.Core.Config import settings
from tequio.Core.Cron import Cron as CronModule
from tequio.Core.Cron import cron_task


@pytest.fixture(autouse=True)
def _reset_redis_client() -> Iterator[None]:
    """El cliente redis se cachea module-level: lo reseteamos para que tome el LOCK_URL
    muerto de cada caso y no se filtre entre tests."""
    CronModule._redis_client = None
    yield
    CronModule._redis_client = None


def test_lock_store_caido_levanta_error_accionable(monkeypatch: MonkeyPatch) -> None:
    # Puerto muerto: nadie escucha en 6390 -> ConnectionError al adquirir el lock.
    monkeypatch.setattr(settings, "lock_url", "redis://127.0.0.1:6390/0")

    @cron_task(name="test.cron.lock_down", without_overlapping=True)
    def task() -> str:
        return "ran"

    with pytest.raises(RuntimeError) as excinfo:
        task()

    message = str(excinfo.value)
    assert "LOCK_URL" in message  # el dev sabe QUÉ configurar
    assert "without_overlapping" in message  # y POR QUÉ se exige
