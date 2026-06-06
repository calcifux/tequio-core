"""Unit tests del engine agnóstico (sin BD). Espeja app/Core/Database/Session.py.

Cubre: el offset de zona, y que la sentencia de zona de sesión se elija POR DIALECTO
(MySQL/Postgres/Oracle) y haga no-op donde no aplica (SQLite, SQL Server). La
ejecución real contra Postgres/Oracle se valida aparte (no hay esos motores en CI).
"""

from __future__ import annotations

import re

from tequio.Core.Database.Session import _app_timezone_offset, _set_timezone_statement


def test_app_timezone_offset_has_signed_hhmm_format() -> None:
    # De TIMEZONE (ej. America/Mexico_City) deriva un offset tipo "-06:00".
    offset = _app_timezone_offset()
    assert re.fullmatch(r"[+-]\d{2}:\d{2}", offset), offset


def test_mysql_uses_offset() -> None:
    statement = _set_timezone_statement("mysql")
    assert statement is not None and statement.startswith("SET time_zone = '")


def test_postgresql_uses_iana_name() -> None:
    statement = _set_timezone_statement("postgresql")
    assert statement is not None and statement.startswith("SET TIME ZONE '")


def test_oracle_uses_alter_session() -> None:
    statement = _set_timezone_statement("oracle")
    assert statement is not None and statement.startswith("ALTER SESSION SET TIME_ZONE = '")


def test_engines_without_session_timezone_are_noop() -> None:
    # SQLite y SQL Server no tienen zona por sesión -> el hook no ejecuta nada.
    assert _set_timezone_statement("sqlite") is None
    assert _set_timezone_statement("mssql") is None
