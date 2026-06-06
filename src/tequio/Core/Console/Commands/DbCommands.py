"""Command `db fresh`: recrea la BD desde cero (baja todo → re-migra → siembra).

Atajo de desarrollo (= `php artisan migrate:fresh --seed`): downgrade a base, upgrade a head y
corre los seeders, en una sola corrida. Es DESTRUCTIVO: borra todos los datos.
"""

from __future__ import annotations

import typer

from tequio.Core.Console import console_command
from tequio.Core.Database.Migrations import run_downgrade, run_upgrade


@console_command(
    name="fresh",
    group="db",
    help="Recrea la BD: baja todo, re-migra y siembra. DESTRUCTIVO. (≈ php artisan migrate:fresh --seed)",
)
def db_fresh(force: bool = typer.Option(False, "--force", help="No pedir confirmación (CI/scripts).")) -> None:
    if not force:
        typer.confirm("Esto BORRA todos los datos (downgrade a base). ¿Continuar?", abort=True)
    run_downgrade("base")  # tira todas las tablas administradas por Alembic
    run_upgrade("head")  # las vuelve a crear
    from tequio.Core.Console.Commands.SeedCommands import db_seed  # lazy: evita ciclos de import

    db_seed()  # corre los seeders
