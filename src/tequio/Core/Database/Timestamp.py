"""Timestamps automáticos DECLARATIVOS (estilo `$table->timestamps()` de Laravel
o `@CreationTimestamp`/`@UpdateTimestamp` de JPA/Hibernate).

La hora la pone la BD con `func.now()` (server-side), y la CONEXIÓN ya corre en
la zona de la app (ver `tequio.Core.Database.Session` → `_set_timezone_statement`,
que la fija según el dialecto: MySQL/Postgres/Oracle). Así los timestamps salen en
hora local sin que Python intervenga ni haya que importar un reloj: cero acoplamiento.
(En SQLite no hay zona de sesión → quedarían en UTC; solo afecta dev/tests.)

- created_at: se setea al INSERT.
- updated_at: se setea al INSERT y se REFRESCA en cada UPDATE (igual que Eloquent).

Opt-in por modelo (como SoftDeleteMixin): solo lo hereda un modelo cuya tabla
tiene ambas columnas.  class Invoice(TimestampMixin, SoftDeleteMixin, Base): ...
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
