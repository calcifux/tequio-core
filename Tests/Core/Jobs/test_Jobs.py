"""Tests de @job (background on-demand), sin broker ni BD."""

from __future__ import annotations

import pytest
from kombu.exceptions import OperationalError
from pytest import MonkeyPatch

from tequio.Core.CeleryApp import QueueUnavailableError
from tequio.Core.Config import settings
from tequio.Core.Jobs import Job, job


def test_job_returns_handle_and_runs_sync() -> None:
    @job(name="test.jobs.add")
    def add(a: int, b: int) -> int:
        return a + b

    assert isinstance(add, Job)
    assert add(2, 3) == 5  # llamada directa = síncrona (no encola)


def test_job_auto_names_from_module_and_func() -> None:
    @job(name="test.jobs.autoname")
    def my_task() -> None: ...

    assert my_task.name == "test.jobs.autoname"  # delegado al Task de Celery


def test_job_rejects_schedule() -> None:
    with pytest.raises(ValueError, match="cron_task"):

        @job(name="test.jobs.bad", schedule="*/5 * * * *")
        def nope() -> None: ...


def test_dispatch_is_broker_guarded(monkeypatch: MonkeyPatch) -> None:
    @job(name="test.jobs.guarded")
    def work(x: int) -> None: ...

    def boom(**_kwargs: object) -> object:
        raise OperationalError("broker down")

    monkeypatch.setattr(work._task, "apply_async", boom)
    with pytest.raises(QueueUnavailableError):
        work.dispatch(x=1)


def test_dispatch_passes_args_and_queue(monkeypatch: MonkeyPatch) -> None:
    @job(name="test.jobs.routed", queue="emails")
    def work(x: int) -> None: ...

    seen: dict[str, object] = {}

    def record(*, args: object, kwargs: object, queue: object) -> str:
        seen.update(args=args, kwargs=kwargs, queue=queue)
        return "task-id"

    monkeypatch.setattr(work._task, "apply_async", record)
    work.dispatch(5)
    assert seen["args"] == [5]
    assert seen["queue"] == "emails"  # cola por defecto del job


def test_dispatch_qualifies_queue_with_namespace(monkeypatch: MonkeyPatch) -> None:
    """Con QUEUE_NAMESPACE la cola del job se prefija ('emails' -> 'miapp.emails'), para que
    dos apps en el mismo broker no compartan la cola. Sin ns viaja tal cual (retrocompatible)."""
    monkeypatch.setattr(settings, "queue_namespace", "miapp")

    @job(name="test.jobs.ns", queue="emails")
    def work(x: int) -> None: ...

    seen: dict[str, object] = {}
    monkeypatch.setattr(work._task, "apply_async", lambda **k: seen.update(k))

    work.dispatch(1)
    assert seen["queue"] == "miapp.emails"  # la cola por defecto del job, namespaceada


def test_dispatch_default_queue_none_stays_none_with_namespace(monkeypatch: MonkeyPatch) -> None:
    """Un job SIN cola por defecto encola con queue=None aun con ns: la default la aísla
    task_default_queue, no el prefijo (None nunca se prefija)."""
    monkeypatch.setattr(settings, "queue_namespace", "miapp")

    @job(name="test.jobs.ns_default")
    def work() -> None: ...

    seen: dict[str, object] = {}
    monkeypatch.setattr(work._task, "apply_async", lambda **k: seen.update(k))

    work.dispatch()
    assert seen["queue"] is None  # None pasa como None; la default la cubre task_default_queue
