"""Command `schedule run`: el `php artisan schedule:run` de Laravel, en Python.

Lo dispara el crontab del SO cada minuto (una sola línea: `* * * * * … schedule run`).
En cada corrida: mira el reloj, recorre los crons agendados (los `@cron_task(schedule=...)`),
y para los que TOCAN este minuto —y cuyo `environments` aplica— los DESPACHA al worker
(`queue work`). Stateless: arranca limpio, despacha, y sale en milisegundos. El trabajo
pesado lo hace el worker (con reintentos/observabilidad de Celery), no este proceso.

Es la vía estilo crontab-del-SO. ALTERNATIVA a `schedule work` (el beat de Celery),
que ahora también agenda los `@cron_task`: elige UNA de las dos (beat O schedule
run), no ambas, o cada cron se despacharía dos veces.
"""

from __future__ import annotations

import typer
from croniter import croniter
from loguru import logger

from tequio.Core.CeleryApp import broker_guard, qualified_queue
from tequio.Core.Clock import SystemClock
from tequio.Core.Config import settings
from tequio.Core.Console import console_command
from tequio.Core.Cron import registered_crons
from tequio.Core.Logging import setup_logging


@console_command(
    name="run",
    group="schedule",
    help="Despacha los crons que tocan este minuto. (≈ php artisan schedule:run)",
)
def schedule_run() -> None:
    """Evalúa qué crons tocan ahora y los manda a la cola. = `schedule:run` de Laravel."""
    setup_logging()
    # Reloj en la zona de la app; al minuto exacto para que croniter haga match limpio.
    now = SystemClock().now().replace(second=0, microsecond=0)

    dispatched: list[str] = []
    for cron in registered_crons():
        # Mismo gate que @cron_task: si el entorno no aplica, ni lo despachamos.
        if cron.environments and settings.app_env not in cron.environments:
            continue
        if croniter.match(cron.schedule, now):
            with broker_guard():  # error claro si redis no está
                if cron.queue is not None:
                    # qualified_queue aplica el QUEUE_NAMESPACE (bus compartido) si hay.
                    cron.task.apply_async(queue=qualified_queue(cron.queue))  # a su cola (= onQueue de Laravel)
                else:
                    cron.task.delay()  # cola por defecto (la aísla task_default_queue con ns)
            dispatched.append(cron.name)

    logger.info("schedule run | despachados: {n} {names}", n=len(dispatched), names=dispatched)
    typer.echo(f"schedule run | {now:%Y-%m-%d %H:%M} | despachados: {len(dispatched)} -> {dispatched}")
