"""Tests del command `schedule run` (despacha los crons que tocan este minuto).

DB-free y sin Redis: congelamos el reloj (monkeypatch a SystemClock.now) y
monkeypatcheamos `.delay()` de cada cron para CAPTURAR a quién se despacharía, sin
tocar el broker. Llamamos a la función directo (el @console_command la deja intacta).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from pytest import MonkeyPatch

from tequio.Core.Clock import SystemClock
from tequio.Core.Config import settings
from tequio.Core.Console.Commands.ScheduleRunCommand import schedule_run
from tequio.Core.Cron import cron_task, every_minute, registered_crons, reset_cron_registry


@pytest.fixture(autouse=True)
def _isolated_cron_registry() -> Iterator[None]:
    """Aísla el registro de crons: arranca y termina limpio, así no se cuelan los
    crons de otros módulos (p. ej. CFDI) registrados al importar."""
    reset_cron_registry()
    yield
    reset_cron_registry()


def _capture_dispatch(monkeypatch: MonkeyPatch, dispatched: list[str]) -> None:
    """Monkeypatchea el .delay() de cada cron registrado para capturar su nombre."""
    for cron in registered_crons():
        name = cron.name
        monkeypatch.setattr(cron.task, "delay", lambda name=name: dispatched.append(name))


def _freeze_now(monkeypatch: MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(SystemClock, "now", lambda self: moment)


def test_dispatches_only_the_crons_due_this_minute(monkeypatch: MonkeyPatch) -> None:
    @cron_task(name="test.always", schedule=every_minute())
    def always_task() -> str:
        return "ran"

    @cron_task(name="test.jan_first", schedule="0 0 1 1 *")  # solo 1-ene 00:00
    def jan_first_task() -> str:
        return "ran"

    dispatched: list[str] = []
    _capture_dispatch(monkeypatch, dispatched)
    _freeze_now(monkeypatch, datetime(2026, 5, 29, 10, 30, 45))  # no es 1-ene

    schedule_run()

    assert dispatched == ["test.always"]  # el de cada minuto sí; el de 1-ene no


def test_skips_crons_whose_environment_does_not_apply(monkeypatch: MonkeyPatch) -> None:
    @cron_task(name="test.wrong_env", schedule=every_minute(), environments=["__never__"])
    def wrong_env_task() -> str:
        return "ran"

    dispatched: list[str] = []
    _capture_dispatch(monkeypatch, dispatched)
    _freeze_now(monkeypatch, datetime(2026, 5, 29, 10, 30, 0))

    schedule_run()

    assert dispatched == []  # toca este minuto, pero el entorno no aplica -> no se despacha


def test_routes_to_the_declared_queue(monkeypatch: MonkeyPatch) -> None:
    @cron_task(name="test.emails", schedule=every_minute(), queue="emails")
    def email_task() -> str:
        return "ran"

    captured: dict[str, str | None] = {}
    cron = registered_crons()[0]
    monkeypatch.setattr(cron.task, "apply_async", lambda queue=None, **kwargs: captured.update(queue=queue))
    _freeze_now(monkeypatch, datetime(2026, 5, 29, 10, 30, 0))

    schedule_run()

    assert captured["queue"] == "emails"  # se despacha a su cola (= ->onQueue('emails'))


def test_routes_to_namespaced_queue_with_namespace(monkeypatch: MonkeyPatch) -> None:
    """Con QUEUE_NAMESPACE, el despacho del cron prefija su cola ('emails' -> 'miapp.emails'),
    para que dos apps en el mismo broker no compartan la cola del cron."""
    monkeypatch.setattr(settings, "queue_namespace", "miapp")

    @cron_task(name="test.emails.ns", schedule=every_minute(), queue="emails")
    def email_task() -> str:
        return "ran"

    captured: dict[str, str | None] = {}
    cron = registered_crons()[0]
    monkeypatch.setattr(cron.task, "apply_async", lambda queue=None, **kwargs: captured.update(queue=queue))
    _freeze_now(monkeypatch, datetime(2026, 5, 29, 10, 30, 0))

    schedule_run()

    assert captured["queue"] == "miapp.emails"  # cola del cron namespaceada
