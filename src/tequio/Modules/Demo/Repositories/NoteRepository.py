"""Repositorio de notas (lecturas tipadas estilo Spring Data).

`NoteRepository` hereda de `Repository[Note, int]`: trae `all()`/`find()`/`paginate()`… del base.
En milpa tenía un `for_owner(owner_id)` (las notas de un dueño); ya no hay dueño en tequio
(worker-side, sin Auth), así que se eliminó: el discovery/jobs usan `all()`.
"""

from __future__ import annotations

from tequio.Core.Database import Repository
from tequio.Models.Note import Note


class NoteRepository(Repository[Note, int]):
    model = Note
