"""Job de background ON-DEMAND del demo: "exportar las notas".

Demuestra `@job` (≠ cron): lo DISPARAS tú con `export_user_notes.dispatch()` y lo corre
`queue work` (no bloquea el llamador). Aquí solo cuenta + loguea; en un caso real
generaría un CSV/ZIP y lo mandaría por correo (trabajo pesado fuera del ciclo del request).

Se auto-registra (el discovery importa todo el árbol del módulo); distinto de los crons (Crons/):
los jobs los disparas tú, los crons los agenda el scheduler.
"""

from __future__ import annotations

from loguru import logger

from tequio.Core.Jobs import job
from tequio.Modules.Demo.Repositories.NoteRepository import NoteRepository


@job(name="demo.export_notes", queue="exports")
def export_user_notes() -> dict[str, int]:
    """Corre en el WORKER: reúne las notas (el 'export' real iría aquí). En milpa exportaba
    las de un dueño (`for_owner(user_id)`); ya no hay dueño en tequio, así que exporta todas."""
    notes = NoteRepository().all()
    logger.info("demo.export_notes | {n} notas exportadas (en el worker)", n=len(notes))
    return {"exported": len(notes)}
