"""Commands `migrate ...`: migraciones de esquema con Alembic (≈ `php artisan migrate`).

Invocación estilo grupo (como `queue work` / `schedule work`):

    jornal migrate make -m "crear tabla facturas"   # genera una revisión (autogenerate)
    jornal migrate run                                # aplica las pendientes (upgrade head)
    jornal migrate status                             # revisión actual + historial
    jornal migrate rollback                           # revierte una revisión (downgrade -1)

La BD sale de `DATABASE_URL` (Settings) y los modelos de `app/Models` (el autogenerate
compara `Base.metadata` contra el esquema real). El archivo generado queda en
`migrations/versions/` para que lo revises antes de aplicarlo.
"""

from __future__ import annotations

import typer

from tequio.Core.Console import console_command
from tequio.Core.Database.Migrations import make_revision, run_downgrade, run_upgrade, show_current, show_history


@console_command(
    name="make",
    group="migrate",
    help="Genera una migración (autogenerate desde los modelos). (≈ php artisan make:migration)",
)
def migrate_make(
    message: str = typer.Option(..., "-m", "--message", help="Descripción corta de la migración."),
    autogenerate: bool = typer.Option(
        True,
        "--autogenerate/--empty",
        help="Detectar cambios de los modelos vs el esquema (o crear una migración vacía).",
    ),
) -> None:
    """Crea el archivo de revisión en migrations/versions/ (revísalo antes de aplicarlo)."""
    make_revision(message, autogenerate=autogenerate)


@console_command(
    name="run",
    group="migrate",
    help="Aplica las migraciones pendientes. (≈ php artisan migrate)",
)
def migrate_run(
    to: str = typer.Option("head", "--to", help="Revisión objetivo (default: head = todas)."),
) -> None:
    """Aplica las migraciones hasta la revisión objetivo."""
    run_upgrade(to)


@console_command(
    name="status",
    group="migrate",
    help="Muestra la revisión aplicada y el historial. (≈ php artisan migrate:status)",
)
def migrate_status() -> None:
    """Equivale a `alembic current` + `alembic history`."""
    show_current(verbose=True)
    show_history()


@console_command(
    name="rollback",
    group="migrate",
    help="Revierte migraciones. (≈ php artisan migrate:rollback)",
)
def migrate_rollback(
    to: str = typer.Option("-1", "--to", help="Revisión objetivo (default: -1 = una atrás)."),
) -> None:
    """Revierte hasta la revisión objetivo."""
    run_downgrade(to)
