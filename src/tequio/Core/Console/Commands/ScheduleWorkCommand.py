"""Command `schedule work`: arranca el DESPERTADOR (beat) de Celery.

beat solo MARCA LA HORA: lee el beat_schedule y, cuando toca, despacha los crons al
worker (que es quien hace el trabajo). NO ejecuta nada por sí mismo. Debe correr UNA
sola instancia (si hubiera varias, cada cron se dispararía varias veces).

Ese beat_schedule lo arma el Registry al configurarse Celery, fusionando los
`@cron_task(schedule=...)` descubiertos (convertidos a crontab) MÁS los
`beat_schedule` declarados en `Console/Kernel.py` (estos con precedencia en
colisión de nombre). Por eso arrancar el beat YA agenda los `@cron_task` sin
necesidad de un Kernel.py.

⚠️ Arrancar esto SÍ dispara los crons, según el guard `@cron_task(environments=
[...])` de cada uno (el guard corre al EJECUTAR en el worker). En dev normalmente
NO lo corres: pruebas a mano con el command directo (p. ej. el command de un
módulo). En prod corre como su propio servicio, separado de los workers (best
practice de Celery). Es la alternativa al `schedule run` disparado por el crontab
del SO: elige UNA vía (beat O schedule run), no ambas, o el cron se despacharía dos
veces.
"""

from __future__ import annotations

import typer

from tequio.Core.CeleryApp import celery_app
from tequio.Core.Config import settings
from tequio.Core.Console import console_command


@console_command(
    name="work",
    group="schedule",
    help="Arranca el scheduler/beat (despacha los crons). (≈ php artisan schedule:work)",
)
def schedule_work(
    loglevel: str = typer.Option(settings.log_level, help="Nivel de log del scheduler."),
    schedule_file: str | None = typer.Option(
        None,
        "--schedule-file",
        help="Dónde persiste el beat su calendario (default: ./celerybeat-schedule del CWD — en "
        "contenedores con el repo montado, apúntalo fuera, p. ej. /tmp/celerybeat-schedule).",
    ),
) -> None:
    """Lanza beat (proceso de larga duración). Bloquea hasta Ctrl-C. El
    beat_schedule lo arma el Registry al configurarse Celery, fusionando DOS
    fuentes: los `@cron_task` descubiertos (convertidos a crontab) MÁS los
    `beat_schedule` declarados en cada `Console/Kernel.py` (estos con precedencia).

    `--schedule-file` reubica el archivo de estado de beat (`-s` de Celery). Útil
    en docker con el repo montado de solo-lectura: el default cae en el CWD y beat
    no podría escribirlo; apúntalo a un volumen escribible (p. ej. /tmp)."""
    argv = ["beat", "--loglevel", loglevel]
    if schedule_file is not None:
        argv += ["-s", schedule_file]  # = celery beat -s <ruta>: dónde persiste su calendario
    celery_app.start(argv=argv)
