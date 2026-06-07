"""Cron AGENDADO del demo: resumen diario de notas (el PRIMER ejemplo de cron en tequio).

Demuestra `@cron_task` (≠ job): lo AGENDA el scheduler — `schedule run` (que el crontab del SO
dispara cada minuto) lo manda al worker cuando toca (8:00 AM). `output="demo_digest"` rutea sus
logs a `logs/cron_demo_digest.log` (diario). Cuenta las notas y MANDA el resumen por correo al
admin (tequio nació para que los crons puedan mandar correo): con el driver `log` (default dev)
el correo se vuelca al log sin SMTP; con `mailpit` (docker compose) se ve en su UI.

Se auto-registra (el discovery importa todo el árbol del módulo) y lo despacha `schedule run`;
distinto de los jobs (Jobs/): los crons los AGENDA el scheduler, no los disparas tú.

`environments=("local", "development")` es un CINTURÓN: aunque alguien apuntara MODULES_PACKAGE
al Demo del framework en producción (app_env "qa"/"production"), el digest NO se agenda ni corre
ahí — el gate de entorno de `@cron_task` lo omite. El Demo es ejemplo de dev, no carga de prod.
"""

from __future__ import annotations

from loguru import logger

from tequio.Core.CeleryApp import QueueUnavailableError
from tequio.Core.Cron import cron_task, daily_at
from tequio.Core.Mail import Mail
from tequio.Modules.Demo.Mail.DailyDigestMailable import DailyDigestMailable
from tequio.Modules.Demo.Repositories.NoteRepository import NoteRepository

# Destinatario del digest. Sin dueño/usuario en tequio (worker-side, sin Auth): es un correo de
# EJEMPLO. En un proyecto real saldría de settings o de la BD (la lista de admins/suscriptores).
_DIGEST_TO = "admin@example.com"


@cron_task(
    name="demo.daily_digest",
    schedule=daily_at("08:00"),
    environments=("local", "development"),
    output="demo_digest",
)
def daily_digest() -> None:
    """Corre en el WORKER cada día a las 8:00 (lo despacha `schedule run`)."""
    total = len(NoteRepository().all())
    logger.info("demo.daily_digest | {n} notas en total (resumen diario)", n=total)
    # Manda el resumen por correo. Worker-side lo idiomático es ENCOLAR (Mail.queue); si el broker
    # no está, caemos a envío SÍNCRONO (Mail.send) — mismo patrón que el dispatch de Events. Con
    # driver=log ninguna rama toca SMTP (el correo va al log); con mailpit y sin broker, el except
    # evita que el cron reviente por falta de redis.
    #
    # Convención de cola: los correos van a la cola `emails` (= `->onQueue('emails')` de Laravel),
    # separada de la cola por defecto para poder darles su propio worker. Se consume con
    # `queue work --queue emails` (o `--queue emails,celery` para drenar también la default).
    # El fallback síncrono ante QueueUnavailableError NO toca la cola (manda en el acto).
    mailable = DailyDigestMailable(total=total)
    try:
        # init_kwargs OBLIGADO al encolar: el worker REINSTANCIA el Mailable desde primitivas
        # (class_path + kwargs), no recibe esta instancia. Deben ser EXACTAMENTE los args del
        # __init__ (= SerializesModels de Laravel). El fallback síncrono no los necesita: usa
        # la instancia ya construida.
        Mail.queue(mailable, to=[_DIGEST_TO], queue="emails", init_kwargs={"total": total})
    except QueueUnavailableError:
        Mail.send(mailable, to=[_DIGEST_TO])
