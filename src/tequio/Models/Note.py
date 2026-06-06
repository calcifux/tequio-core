"""Modelo Note del demo: una nota simple (título, cuerpo y archivado lógico).

En milpa la nota tenía DUEÑO (`owner_id`, FK a users con ABAC); tequio es worker-side
sin Auth, así que el rastro del dueño se ELIMINÓ por completo (era la cicatriz de Auth):
queda una nota pelada que luce el stack worker-side sin arrastrar conceptos web.
"""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from tequio.Core.Database import Base, TimestampMixin


class Note(TimestampMixin, Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(default="")
    body: Mapped[str] = mapped_column(default="")
    # Archivado lógico (lo alterna el comando ArchiveNote vía [[Mediator]]); por default activa.
    archived: Mapped[bool] = mapped_column(default=False)
