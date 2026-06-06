"""Engine y fábrica de sesiones, AGNÓSTICOS del motor SQL.

El motor se elige por `DATABASE_URL` (mysql+pymysql, postgresql+psycopg,
oracle+oracledb, mssql+pyodbc, sqlite). Todo lo ESPECÍFICO por dialecto está
AISLADO en este archivo (la regla del plan: no regar SQL de un motor por el código):
  - `_engine_kwargs()`: kwargs de create_engine que difieren (SQLite necesita
    connect_args/StaticPool; los cliente-servidor usan pool_pre_ping/recycle).
  - `_set_timezone_statement()`: cada motor fija la zona de la sesión distinto.

El acceso a la sesión va por la sesión AMBIENTE (`Transactional`): `@transactional`
(commit/rollback) o `session_scope` (manual); los repos la toman con `current_session()`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tequio.Core.Config import settings

# Backend (dialecto) derivado de la URL: "mysql" | "postgresql" | "oracle" | "mssql" | "sqlite".
_url = make_url(settings.database_url)
_backend = _url.get_backend_name()


def _engine_kwargs() -> dict[str, Any]:
    """kwargs de `create_engine` que difieren por dialecto."""
    if _backend == "sqlite":
        # SQLite: la conexión puede cruzar hilos (FastAPI/worker), y en memoria hay
        # que compartir UNA conexión (si no, cada conexión es una BD vacía distinta).
        kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
        if _url.database in (None, "", ":memory:"):
            kwargs["poolclass"] = StaticPool
        return kwargs
    # Motores cliente-servidor (mysql/postgres/oracle/mssql): pool robusto para
    # procesos longevos (workers): verifica la conexión y recicla cada hora.
    return {"pool_pre_ping": True, "pool_recycle": 3600}


engine = create_engine(settings.database_url, **_engine_kwargs())


def _app_timezone_offset() -> str:
    """Offset de la zona de la app (TIMEZONE del .env), ej. '-06:00'."""
    offset = datetime.now(ZoneInfo(settings.timezone)).strftime("%z")  # "-0600"
    return f"{offset[:3]}:{offset[3:]}"


def _set_timezone_statement(dialect_name: str) -> str | None:
    """SQL para fijar la zona de la CONEXIÓN a la zona de la app, POR DIALECTO.

    Así `NOW()/CURRENT_TIMESTAMP` y los timestamps automáticos (`func.now()` del
    TimestampMixin) salen en hora local sin que Python intervenga. Devuelve None si
    el motor NO tiene zona por sesión (SQLite, SQL Server) → el hook hace no-op.

    Notas por motor:
      - MySQL/MariaDB: offset (los nombres IANA exigen cargar las tz tables).
      - PostgreSQL: nombre IANA (Postgres trae las zonas; más robusto que el offset).
      - Oracle: offset vía ALTER SESSION.
      - SQLite: sin zona de sesión → CURRENT_TIMESTAMP queda en UTC (aceptable en dev/tests).
    """
    if dialect_name in ("mysql", "mariadb"):
        return f"SET time_zone = '{_app_timezone_offset()}'"
    if dialect_name == "postgresql":
        return f"SET TIME ZONE '{settings.timezone}'"
    if dialect_name == "oracle":
        return f"ALTER SESSION SET TIME_ZONE = '{_app_timezone_offset()}'"
    return None  # sqlite, mssql: sin zona por sesión


@event.listens_for(engine, "connect")
def _set_session_timezone(dbapi_connection: Any, _connection_record: Any) -> None:
    statement = _set_timezone_statement(engine.dialect.name)
    if statement is None:
        return  # el motor no soporta zona por sesión: no-op
    cursor = dbapi_connection.cursor()
    cursor.execute(statement)
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
