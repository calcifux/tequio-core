"""Tests de @job (background on-demand), sin broker ni BD."""

from __future__ import annotations

import pytest
from kombu.exceptions import OperationalError
from pytest import MonkeyPatch

from tequio.Core.CeleryApp import QueueUnavailableError
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
