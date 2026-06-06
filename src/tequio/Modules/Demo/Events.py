"""Eventos de DOMINIO del demo (= Events de Laravel). NO atados a la BD: se disparan
EXPLÍCITamente con `dispatch(NoteCreated(...))` desde el servicio, no por un commit.

Contrato (ver [[Core/Events/Tasks]]): un evento es un `@dataclass` de PRIMITIVOS planos. Si hay
broker, viaja como kwargs JSON y el worker lo reconstruye con `Evento(**kwargs)`; sin broker corre
síncrono. Por eso NUNCA lleva instancias ORM ni sesiones — solo ids y strings.

Quién los observa: `Observers/` (1:N). Aquí solo se DECLARAN los hechos.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NoteCreated:
    """Se creó una nota. Lo observa LogNoteCreated. Viaja con primitivos (`note_id`/`title`)
    porque el observer corre en el worker (sin request): en milpa mandaba correo i18n al dueño
    (y por eso cargaba `owner_id`/`owner_email`/`locale`), pero ya no hay dueño en tequio: se loguea."""

    note_id: int
    title: str
