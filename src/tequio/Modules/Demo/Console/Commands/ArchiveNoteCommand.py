"""Command CLI `demo archive <note_id>`: archiva una nota desde la terminal.

Demuestra el caso de uso transport-NEUTRAL del [[Mediator]]: el MISMO `send(ArchiveNote(...))` que
usaría un Job/servicio corre aquí, sin duplicar la lógica. La CLI es un proceso aparte, así que
asegura a mano el discovery de lo que el caso de uso usa: los HANDLERS (para el Mediator).
"""

from __future__ import annotations

import typer

from tequio.Core.Console import console_command
from tequio.Core.Mediator import send
from tequio.Core.Registry import import_all_handlers
from tequio.Modules.Demo.Commands import ArchiveNote


@console_command(name="archive", help="Archiva una nota (vía Mediator; mismo comando que usaría un Job/servicio).")
def archive_note(note_id: int) -> None:
    """Envía el comando ArchiveNote y reporta el resultado."""
    # La CLI no corre el lifespan: registra a mano lo que el caso de uso necesita.
    import_all_handlers()  # handlers del Mediator (resuelve ArchiveNote -> ArchiveNoteHandler)
    result = send(ArchiveNote(note_id=note_id))
    typer.echo(f"Nota {result['id']} archivada (archived={result['archived']}).")
