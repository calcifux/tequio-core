"""Comandos del demo para el [[Mediator]] (command bus 1:1). Un comando es una INTENCIÓN
que envías con `send(ArchiveNote(...))` y de la que esperas un resultado; lo resuelve UN handler
(`Handlers/`). A diferencia de un evento (1:N, sin retorno), aquí hay 1 handler y retorno.
El mismo `send(ArchiveNote(...))` corre desde la CLI y desde un Job/servicio →
caso de uso transport-neutral, sin duplicar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ArchiveNote:
    """Archivar una nota. En milpa llevaba `actor_id` (quién la archiva) para el ABAC del
    handler; tequio es worker-side sin Auth/Gate, así que se eliminó: solo el `note_id`."""

    note_id: int
