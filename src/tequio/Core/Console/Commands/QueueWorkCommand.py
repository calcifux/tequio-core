"""Command `queue work`: arranca el TRABAJADOR (worker) de Celery.

El worker es el que EJECUTA las tareas en background (mandar correos, timbrar,
etc.). Por sí solo no agenda nada: solo procesa lo que se le despacha. El
"despertador" que dispara los crons va aparte (`schedule work`), a propósito,
para que una laptop de desarrollo nunca dispare crons sola. ≈ `php artisan
queue:work` de Laravel.
"""

from __future__ import annotations

import sys

import typer
from loguru import logger

from tequio.Core.CeleryApp import celery_app
from tequio.Core.Config import settings
from tequio.Core.Console import console_command


@console_command(
    name="work",
    group="queue",
    help="Arranca el worker de Celery (procesa las tareas en background). (≈ php artisan queue:work)",
)
def queue_work(
    queue: str | None = typer.Option(
        None,
        "--queue",
        help="Cola(s) a consumir, separadas por coma (ej: emails,reports). = `queue:work --queue=emails`. "
        "Si se omite, consume la cola por defecto.",
    ),
    concurrency: int | None = typer.Option(None, help="Número de procesos worker en paralelo (default: nº de CPUs)."),
    loglevel: str = typer.Option(settings.log_level, help="Nivel de log del worker."),
    pool: str | None = typer.Option(
        None,
        "--pool",
        help="Pool de ejecución de Celery (prefork, solo, threads, gevent). En Windows, si se omite, "
        "se usa 'solo' automáticamente (el prefork de billiard no es confiable ahí).",
    ),
) -> None:
    """Lanza el worker (proceso de larga duración). Bloquea hasta Ctrl-C.

    NO embebe el scheduler (`-B`) de forma deliberada: el despertador se arranca
    aparte con `schedule work`, así dev no auto-dispara crons.
    """
    if pool is None and sys.platform == "win32":
        # En Windows el prefork de billiard no es confiable: caemos a 'solo' por defecto.
        pool = "solo"
        logger.info("queue work | Windows detectado: usando pool 'solo' (prefork de billiard no es confiable ahí)")
    argv = ["worker", "--loglevel", loglevel]
    if queue is not None:
        argv += ["-Q", queue]  # = --queue=emails de Laravel; consume solo esa(s) cola(s)
    if concurrency is not None:
        argv += ["--concurrency", str(concurrency)]
    if pool is not None:
        argv += ["--pool", pool]
    celery_app.worker_main(argv=argv)
