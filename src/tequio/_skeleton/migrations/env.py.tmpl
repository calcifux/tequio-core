"""Entorno de Alembic para tequio.

NO usa alembic.ini: la Config se arma en código (tequio.Core.Database.Migrations) y aquí
tomamos la BD y los modelos de la ÚNICA fuente de verdad del framework:
  - `settings.database_url` (Settings ← .env) para la conexión,
  - `Base.metadata` poblada por `import_all_models()` (mismo discovery que la app) como
    objetivo del autogenerate.

Reusa el `engine` del framework (un solo lugar arma el engine, agnóstico del motor).
"""

from __future__ import annotations

from alembic import context

from tequio.Core.Config import settings
from tequio.Core.Database import Base, engine
from tequio.Core.Registry import import_all_models

# Importa TODOS los modelos compartidos para que Base.metadata esté completa antes del
# autogenerate (si no, Alembic creería que "no hay tablas" y generaría migraciones vacías).
import_all_models()
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Modo offline (`--sql`): emite el SQL sin conectarse, usando la URL de Settings."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # detecta cambios de TIPO de columna, no solo de nombre
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo online (normal): corre contra la BD reusando el engine del framework."""
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
