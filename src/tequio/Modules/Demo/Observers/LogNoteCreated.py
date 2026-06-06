"""Observers del demo (Listeners 1:N). Se auto-registran al importarse (el discovery importa
todo el árbol del módulo en el arranque) y los dispara `Events.dispatch(...)`. Transporte
adaptativo: corren en el worker si hay broker, si no síncrono — sin que el observer lo sepa.

Reaccionan a `NoteCreated` (1:N). No tocan BD: todo lo que necesitan viene en el evento.
"""

from __future__ import annotations

from loguru import logger

from tequio.Core.Events import Observer
from tequio.Modules.Demo.Events import NoteCreated


class LogNoteCreated(Observer):
    """Loguea la creación de una nota. En milpa esto era un Mailable i18n al DUEÑO
    (`NotifyOwnerOnNoteCreated`); ya no hay dueño en tequio (worker-side, sin Auth):
    el observer solo loguea el hecho."""

    observes = NoteCreated

    def handle(self, event: object) -> None:
        assert isinstance(event, NoteCreated)  # dispatch ya filtró por tipo; narrow para mypy
        # en milpa esto era un Mailable i18n al dueño; tequio es worker-side: se loguea
        logger.info(
            'demo.note_created | nota {id} "{t}" creada',
            id=event.note_id,
            t=event.title,
        )
