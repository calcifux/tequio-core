"""`@job`: declara una función como JOB de background ON-DEMAND (estilo `Job::dispatch` de Laravel).

NO es un cron y vive en `Core/Jobs` (no `Core/Cron`) a propósito, para no confundir dos modelos
de ejecución distintos:
  - **cron** (`@cron_task`): lo AGENDA el scheduler (beat / `schedule run`); tiene lock
    anti-overlap, env-gating, output routing; NUNCA reintenta (se re-agenda solo).
  - **job** (`@job`): lo DISPARAS tú desde tu código (`mi_job.dispatch(...)`); lo ejecuta
    `queue work`; reintentos OPT-IN para fallos transitorios; sin lock/env/output.

`@job` es un wrapper FINO sobre `@celery_app.task` que: auto-nombra (`<modulo>.<func>`), opta a
`retry_policy` si pasas `retry_for`, y expone `.dispatch()` que enmascara el
`with broker_guard(): task.apply_async(...)` repetitivo (broker caído → `QueueUnavailableError`
= 503 RFC 9457, nunca un drop mudo). Descubrimiento: igual que cualquier task — `import_all_tasks`
importa `Modules/<X>/Jobs/` y el decorador registra la task de Celery; no hay registro nuevo.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from celery import Task

from tequio.Core.CeleryApp import broker_guard, celery_app, retry_policy


class Job:
    """Handle de un job. `.dispatch(...)` lo ENCOLA (broker-guarded); llamarlo directo
    `mi_job(...)` lo corre SÍNCRONO (útil en tests). Delega al `Task` de Celery para uso
    avanzado (`.delay`, `.apply_async`, `.s`, `.si`, ...)."""

    def __init__(self, task: Task, default_queue: str | None) -> None:
        self._task = task
        self._default_queue = default_queue

    def dispatch(self, *args: Any, queue: str | None = None, **kwargs: Any) -> Any:
        """Encola el job en Celery. `broker_guard`: si el broker no responde, lanza
        `QueueUnavailableError` (503) en vez del stacktrace de kombu. = `Job::dispatch`."""
        with broker_guard():
            return self._task.apply_async(args=list(args), kwargs=kwargs, queue=queue or self._default_queue)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Corre el job SÍNCRONO, en el proceso actual (no encola). Útil en tests."""
        return self._task(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # Delega lo no-definido al Task de Celery (.delay, .apply_async, .name, .s, ...).
        return getattr(self._task, name)


def job(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    queue: str | None = None,
    retry_for: tuple[type[BaseException], ...] = (),
    max_retries: int | None = None,
    bind: bool = False,
    schedule: Any = None,
    **celery_options: Any,
) -> Any:
    """Decora una función como job de background on-demand. Uso:

        @job(retry_for=(ConnectionError, TimeoutError))
        def export_notes(user_id: int) -> None: ...

        export_notes.dispatch(user_id=42)   # encola; el worker (`queue work`) lo corre

    `retry_for` vacío = fire-and-forget (sin reintentos). `bind=True` da `self` (para
    `self.request.retries`). `schedule=` está PROHIBIDO: para tareas programadas usa `@cron_task`.
    """
    if schedule is not None:
        raise ValueError("@job es on-demand: para tareas PROGRAMADAS usa @cron_task (Core/Cron), no @job.")

    def decorator(target: Callable[..., Any]) -> Job:
        options: dict[str, Any] = dict(celery_options)
        options["name"] = name or f"{target.__module__}.{target.__name__}"
        if bind:
            options["bind"] = True
        if retry_for:
            options.update(retry_policy(retry_for=retry_for, max_retries=max_retries))
        task: Task = celery_app.task(**options)(target)
        return Job(task, queue)

    if func is not None:  # uso sin paréntesis: @job
        return decorator(func)
    return decorator  # uso con args: @job(...)
