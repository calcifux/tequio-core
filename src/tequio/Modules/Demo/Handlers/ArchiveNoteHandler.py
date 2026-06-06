"""Handlers del [[Mediator]] del demo. Se auto-registran con `@handles(Comando)` al importarse
(el discovery importa todo el árbol del módulo en el arranque); los resuelve `Mediator.send`.

Sacan el caso de uso para reusarlo desde la CLI y desde un Job/servicio con el MISMO
`send(...)`. Devuelven el dict serializado ANTES del commit (evita el detached del
expire_on_commit).
"""

from __future__ import annotations

from typing import Any

from tequio.Core.Database import current_session, transactional
from tequio.Core.Errors import ResourceNotFoundError
from tequio.Core.Mediator import handles
from tequio.Models.Note import Note
from tequio.Modules.Demo.Commands import ArchiveNote
from tequio.Modules.Demo.Services.NoteService import note_dict


@handles(ArchiveNote)
class ArchiveNoteHandler:
    """Marca `archived=True` en la nota."""

    @transactional
    def handle(self, command: ArchiveNote) -> dict[str, Any]:
        note = current_session().get(Note, command.note_id)
        if note is None:
            raise ResourceNotFoundError(f"Nota {command.note_id} no existe", details={"id": command.note_id})
        # en milpa aquí se cargaba el actor y Gate.authorize("note.update") (ABAC dueño/moderador);
        # tequio worker-side no tiene Auth: se archiva directo (sin actor).
        note.archived = True
        return note_dict(note)
