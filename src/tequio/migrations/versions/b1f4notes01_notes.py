"""notes

Revision ID: b1f4notes01
Revises:
Create Date: 2026-06-06

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Identificadores de la revisión, usados por Alembic.
revision: str = "b1f4notes01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Revisión base: SOLO la tabla notes (tequio es worker-side, sin tabla users/Auth).
    # La nota es pelada (id/title/body/archived): se eliminó `owner_id` y su índice, que eran
    # la cicatriz del dueño de milpa (FK a users con ABAC).
    # `archived` lleva server_default=false para que las filas existentes (BD migrada/legacy)
    # tomen valor sin violar NOT NULL; el modelo Note usa default=False client-side, el
    # server_default cubre el backfill de lo ya creado (mismo razonamiento que a7c1d9e2 en milpa).
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
    )


def downgrade() -> None:
    op.drop_table("notes")
