"""Servicio de notas: escrituras en UNA transacción que devuelven un dict ya serializado
(antes del commit, para no chocar con el expire_on_commit / DetachedInstanceError).

`note_dict`/`NoteOut` viven aquí (en milpa estaban en Serializers.py, excluido): serializan el
modelo a dict JSON-able con Pydantic v2, agregando `excerpt` con `computed_field` (campo DERIVADO
que NO vive en la tabla). El handler ArchiveNoteHandler reusa `note_dict`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field

from tequio.Core.Database import current_session, transactional
from tequio.Core.Pipeline import Pipeline
from tequio.Models.Note import Note
from tequio.Modules.Demo.Pipes.CleanContent import CollapseWhitespace, NoteDraft, TrimContent


class NoteOut(BaseModel):
    """Serializador de una nota. `from_attributes` permite `model_validate(note)` (lee el ORM)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    archived: bool = False

    @computed_field  # type: ignore[prop-decorator]  # Pydantic v2: computed sobre @property
    @property
    def excerpt(self) -> str:
        """Vista previa del cuerpo (primeros 80 chars) — DERIVADO, no vive en la tabla."""
        text = self.body.strip()
        return text if len(text) <= 80 else f"{text[:80].rstrip()}…"


def note_dict(note: Note) -> dict[str, Any]:
    """Dict JSON-able de una nota (vía NoteOut/Pydantic v2; incluye `excerpt` computado)."""
    return NoteOut.model_validate(note).model_dump()


# en milpa había update()/delete() con Gate.authorize ABAC (solo el dueño); tequio no tiene Auth: se omiten.
class NoteService:
    @transactional
    def create(self, title: str, body: str) -> dict[str, Any]:
        # estilo milpa: el contenido se NORMALIZA con un Pipeline (etapas componibles) antes de
        # persistir, en vez de strip()/split() sueltos. Ver Pipes/CleanContent.py.
        draft: NoteDraft = (
            Pipeline()
            .send(NoteDraft(title=title, body=body))
            .through([TrimContent(), CollapseWhitespace()])
            .then_return()
        )
        note = Note(title=draft.title, body=draft.body)
        current_session().add(note)
        current_session().flush()  # asigna PK
        return note_dict(note)
