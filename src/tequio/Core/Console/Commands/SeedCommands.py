"""Command `db:seed`: corre los seeders descubiertos (= `php artisan db:seed`).

Cada seeder corre en su PROPIA transacción (commit/rollback), así un fallo no deja a medias
a los demás. Los modelos se importan antes para que estén registrados.
"""

from __future__ import annotations

import typer

from tequio.Core.Console import console_command
from tequio.Core.Database.Seeder import Seeder, registered_seeders
from tequio.Core.Database.Transactional import transactional
from tequio.Core.Registry import import_all_models, import_all_seeders


@transactional
def _run_seeder(seeder: Seeder) -> None:
    seeder.run()


@console_command(name="seed", group="db", help="Corre los seeders (puebla la BD). (≈ php artisan db:seed)")
def db_seed() -> None:
    """Descubre las subclases de Seeder de los módulos y las ejecuta."""
    import_all_models()
    import_all_seeders()
    seeders = registered_seeders()
    if not seeders:
        typer.echo("No hay seeders registrados.")
        return
    for seeder_class in seeders:
        _run_seeder(seeder_class())
        typer.echo(f"✓ Seeded: {seeder_class.__name__}")
