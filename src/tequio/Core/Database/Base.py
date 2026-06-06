"""Base declarativa compartida por TODOS los modelos.

naming_convention estabiliza los nombres de índices/constraints (clave para
Alembic en el futuro). Todos los modelos de app/Models heredan de esta Base.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Convención de nombres recomendada (SQLAlchemy 2.0) para autogenerado estable.
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa 2.0 (tipada). Todos los modelos de app/Models heredan de aquí."""

    metadata = MetaData(naming_convention=naming_convention)
