"""Tests del Filtering DSL (FilterQueryModel), SIN BD: compila a cláusulas SQLAlchemy y se
inspecciona su SQL renderizado (str) — no se ejecuta contra un motor. El modelo usa su PROPIO
DeclarativeBase para no contaminar el Base.metadata del framework.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tequio.Core.Database import FilterQueryModel
from tequio.Core.Errors import InvalidFilterError


class _Base(DeclarativeBase):
    pass


class _Note(_Base):
    __tablename__ = "_notes_filter_test"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(default="")
    body: Mapped[str] = mapped_column(default="")
    owner_id: Mapped[int] = mapped_column(default=0)


class _NoteFilter(FilterQueryModel):
    sa_model = _Note
    search_fields = ("title", "body")
    order_fields = ("id", "title")

    owner_id: int | None = None


def test_where_is_none_when_no_filters() -> None:
    assert _NoteFilter().where() is None


def test_where_field_equality() -> None:
    sql = str(_NoteFilter(owner_id=3).where())
    assert "owner_id" in sql and "=" in sql


def test_where_search_is_or_ilike_across_search_fields() -> None:
    sql = str(_NoteFilter(search="abc").where()).upper()
    assert "TITLE" in sql and "BODY" in sql
    assert "LIKE" in sql and " OR " in sql


def test_where_combines_field_and_search_with_and() -> None:
    sql = str(_NoteFilter(owner_id=1, search="abc").where()).upper()
    assert " AND " in sql


def test_order_by_desc_prefix() -> None:
    sql = str(_NoteFilter(ordering="-title").order_by()).upper()
    assert "TITLE" in sql and "DESC" in sql


def test_order_by_asc_default() -> None:
    sql = str(_NoteFilter(ordering="id").order_by()).upper()
    assert "ASC" in sql


def test_order_by_none_when_not_requested() -> None:
    assert _NoteFilter().order_by() is None


def test_order_by_rejects_field_outside_whitelist() -> None:
    with pytest.raises(InvalidFilterError) as exc_info:
        _NoteFilter(ordering="secret").order_by()
    error = exc_info.value
    assert error.status_code == 422
    assert error.error_code == "invalid_filter"
    assert error.details == {"field": "secret", "allowed": ["id", "title"]}


def test_apply_chains_where_and_order_on_select() -> None:
    sql = str(_NoteFilter(owner_id=1, ordering="-id").apply(select(_Note))).upper()
    assert "WHERE" in sql and "ORDER BY" in sql
