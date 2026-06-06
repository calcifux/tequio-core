"""Tasks de cron con semántica del scheduler de Laravel.

`@cron_task` registra una task de Celery y le agrega, de forma declarativa, lo
mismo que `$schedule->command(...)->...`:

- `environments=[...]`   ≈ ->environments([...])   : solo corre si APP_ENV está en la lista.
- `without_overlapping`  ≈ ->withoutOverlapping()  : lock en Redis; si la corrida
                                                      anterior sigue, esta se omite.
- `output="reporte_nocturno"` ≈ ->appendOutputTo(...) : rutea los logs de la corrida a
                                                      logs/cron_reporte_nocturno.log (diario).

- `schedule="*/5 * * * *"` ≈ ->everyFiveMinutes() : la CADENCIA, pegada al job.
  Se evalúa en `schedule run` (lo dispara el crontab del SO cada minuto). Usa los
  helpers de Schedule.py (every_minute(), daily_at(...), etc.) para no escribir
  crudo el cron. El job se registra para que `schedule run` lo descubra.

Las otras dos NO necesitan código:
- ->runInBackground()  : nativo — el scheduler DESPACHA; el worker corre la task.
- ->onOneServer()      : el crontab vive en UN solo server (como en Laravel).
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, TypeVar

import redis
from loguru import logger

from tequio.Core.CeleryApp import celery_app
from tequio.Core.Config import settings
from tequio.Core.Logging import _LOG_FORMAT

DecoratedTask = TypeVar("DecoratedTask", bound=Callable[..., Any])

# Cliente Redis y sinks de log creados perezosamente (una vez por proceso).
_redis_client: redis.Redis | None = None
_cron_log_sinks: set[str] = set()

# Margen (segundos) que el lock de overlapping suma sobre el visibility_timeout del
# broker, cuando no se pasa lock_timeout explícito. Asegura `lock > visibility`.
_LOCK_TIMEOUT_MARGIN_SECONDS = 300


@dataclass(frozen=True)
class RegisteredCron:
    """Un cron declarado con `@cron_task(schedule=...)`, listo para que `schedule run`
    decida si toca y lo despache."""

    name: str
    schedule: str  # expresión cron (5 campos), normalmente de Schedule.py
    environments: tuple[str, ...]  # entornos donde aplica (vacío = todos)
    queue: str | None  # cola de Celery a la que se despacha (None = cola por defecto)
    task: Any  # la task de Celery (para .delay() / .apply_async())


# Registro de crons agendados. Se llena cuando se importan los archivos (el
# decorador corre); `schedule run` lo recorre. Mismo patrón module-level que el
# registro de Console.
_CRON_REGISTRY: list[RegisteredCron] = []


def registered_crons() -> list[RegisteredCron]:
    """Vista de los crons agendados (para `schedule run` y tests)."""
    return list(_CRON_REGISTRY)


def reset_cron_registry() -> None:
    """Limpia el registro de crons. SOLO para tests (aislar casos)."""
    _CRON_REGISTRY.clear()


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        # El lock vive en el LOCK store (redis), independiente del broker (que puede ser
        # RabbitMQ/SQS y no tener primitiva de lock).
        _redis_client = redis.Redis.from_url(settings.effective_lock_url)
    return _redis_client


def _ensure_cron_log_sink(output: str) -> None:
    """Agrega (una sola vez) un archivo de log diario para esta corrida de cron."""
    if output in _cron_log_sinks:
        return
    _cron_log_sinks.add(output)
    logger.add(
        f"{settings.log_dir}/cron_{output}.log",
        level=settings.log_level,
        format=_LOG_FORMAT,
        rotation="00:00",  # archivo nuevo cada día (= createDailyOutput del legacy)
        retention="14 days",
        compression="zip",
        enqueue=True,
        filter=lambda record: record["extra"].get("cron") == output,
    )


def cron_task(
    *,
    name: str,
    schedule: str | None = None,
    queue: str | None = None,
    environments: Sequence[str] | None = None,
    without_overlapping: bool = False,
    output: str | None = None,
    lock_timeout: int | None = None,
    **celery_options: Any,
) -> Callable[[DecoratedTask], Any]:
    """Decora una función como task de Celery con semántica de scheduler de Laravel.

    `schedule` (expresión cron, idealmente vía helpers de Schedule.py): si se pasa,
    el cron se registra para que `schedule run` lo despache cuando toque. Si es None,
    la task existe pero no se agenda (se despacha a mano o desde otro lado).

    `queue`: cola de Celery a la que `schedule run` despacha (= `->onQueue('emails')`
    de Laravel). El worker la consume con `queue work --queue=<cola>`. Si es None,
    va a la cola por defecto.

    `lock_timeout` (solo aplica con without_overlapping): si es None, se deriva de
    `settings.redis_visibility_timeout + margen`. El invariante `lock > visibility`
    queda asegurado por construcción: si fueran iguales, al expirar ambos a la vez
    Redis reentregaría la task y un segundo worker tomaría el lock recién liberado,
    ejecutando el cron DOS veces (doble timbrado). Pasar un lock_timeout explícito
    menor o igual al visibility_timeout es un error y se rechaza al decorar.
    """

    def decorator(func: DecoratedTask) -> Any:
        visibility_timeout = settings.redis_visibility_timeout
        effective_lock_timeout = (
            lock_timeout if lock_timeout is not None else visibility_timeout + _LOCK_TIMEOUT_MARGIN_SECONDS
        )
        if effective_lock_timeout <= visibility_timeout:
            raise ValueError(
                f"cron '{name}': lock_timeout ({effective_lock_timeout}s) debe ser MAYOR que el "
                f"visibility_timeout del broker ({visibility_timeout}s). Si son iguales/menores, un cron "
                f"de larga duración puede ejecutarse dos veces. Sube REDIS_VISIBILITY_TIMEOUT o lock_timeout."
            )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # environments(): no corre en entornos no permitidos.
            if environments is not None and settings.app_env not in environments:
                logger.info("cron {n}: omitido (entorno '{e}' no permitido)", n=name, e=settings.app_env)
                return None

            # appendOutputTo(): rutea los logs de ESTA corrida a su archivo diario.
            if output is not None:
                _ensure_cron_log_sink(output)
            log_context = logger.contextualize(cron=output) if output is not None else nullcontext()

            with log_context:
                if not without_overlapping:
                    return func(*args, **kwargs)

                # withoutOverlapping(): lock en Redis; el timeout evita deadlock si el
                # worker muere a media corrida. blocking=False -> si está tomado, se omite.
                lock = _get_redis().lock(f"cron-lock:{name}", timeout=effective_lock_timeout, blocking=False)
                if not lock.acquire(blocking=False):
                    logger.warning("cron {n}: omitido (la corrida anterior sigue en curso)", n=name)
                    return None
                try:
                    return func(*args, **kwargs)
                finally:
                    try:
                        lock.release()
                    except redis.exceptions.LockError:
                        # El lock ya había expirado por timeout: la corrida tardó más
                        # que lock_timeout. No es error; solo lo dejamos pasar.
                        logger.warning("cron {n}: el lock ya había expirado al liberar", n=name)

        celery_task = celery_app.task(name=name, **celery_options)(wrapper)
        if schedule is not None:
            _CRON_REGISTRY.append(
                RegisteredCron(
                    name=name,
                    schedule=schedule,
                    environments=tuple(environments) if environments is not None else (),
                    queue=queue,
                    task=celery_task,
                )
            )
        return celery_task

    return decorator
