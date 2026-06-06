"""Pipeline de limpieza del contenido de una nota (modelo cebolla, estilo Laravel).

Un `NoteDraft` (título + cuerpo) fluye por etapas que lo normalizan ANTES de persistir: cada pipe
transforma y llama `next(draft)` para seguir. Demuestra el patrón [[Pipeline]] en un caso real:
en vez de meter `title.strip()` + `" ".join(...)` sueltos en el service, son etapas componibles y
reordenables. Se enchufan en `NoteService.create` con `.through([TrimContent(), CollapseWhitespace()])`.

NO se auto-descubren: se pasan EXPLÍCITOS a `.through([...])` donde se usan, como en Laravel.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class NoteDraft:
    """Lo que viaja por el pipeline: el contenido crudo de la nota, mutable etapa a etapa."""

    title: str
    body: str


class TrimContent:
    """Recorta espacios al inicio/fin del título y del cuerpo."""

    def handle(self, draft: NoteDraft, next: Callable[[Any], Any]) -> Any:  # noqa: A002 — `next` calca a Laravel
        draft.title = draft.title.strip()
        draft.body = draft.body.strip()
        return next(draft)


class CollapseWhitespace:
    """Colapsa los espacios internos del título a uno solo (evita "Hola    mundo")."""

    def handle(self, draft: NoteDraft, next: Callable[[Any], Any]) -> Any:  # noqa: A002
        draft.title = " ".join(draft.title.split())
        return next(draft)
