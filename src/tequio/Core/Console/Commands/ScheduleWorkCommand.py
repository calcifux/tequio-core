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
) -> None:
    """Lanza beat (proceso de larga duración). Bloquea hasta Ctrl-C. El
    beat_schedule lo arma el Registry al configurarse Celery: los `@cron_task`
    descubiertos (convertidos a crontab) más los `beat_schedule` de cada
    `Console/Kernel.py` (estos con precedencia)."""
    celery_app.start(argv=["beat", "--loglevel", loglevel])
