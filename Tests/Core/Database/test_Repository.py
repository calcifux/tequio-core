"""Tests de Repository.find_or_fail / first_or_create, SIN BD.

Se monkeypatchea `SessionLocal` con una sesión FAKE (mismo patrón que test_Transactional):
valida la LÓGICA (raise si no existe; devolver vs crear) sin tocar un motor. El modelo de
prueba usa su PROPIO DeclarativeBase para no contaminar el Base.metadata del framework.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest import MonkeyPatch
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import tequio.Core.Database.Transactional as tx
from tequio.Core.Database.Repository import CursorPage, Repository, _decode_cursor, _encode_cursor
from tequio.Core.Errors import ResourceNotFoundError


class _TestBase(DeclarativeBase):
    pass


class _Widget(_TestBase):
    __tablename__ = "_widgets_test"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(default="")
    color: Mapped[str] = mapped_column(default="")


class _WidgetRepository(Repository[_Widget, int]):
    model = _Widget


class _FakeResult:
    def __init__(self, first: Any = None, rows: Any = None) -> None:
        self._first = first
        self._rows = rows if rows is not None else []

    def scalars(self) -> _FakeResult:
        return self

    def first(self) -> Any:
        return self._first

    def all(self) -> Any:
        return self._rows


class _FakeSession:
    """Sesión fake: get() / execute() devuelven lo configurado; registra add()/flush()."""

    def __init__(self, *, get_result: Any = None, first_result: Any = None, all_result: Any = None) -> None:
        self._get_result = get_result
        self._first_result = first_result
        self._all_result = all_result if all_result is not None else []
        self.added: list[Any] = []
        self.flushed = 0

    # session_scope / @transactional llaman estos:
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...

    # find_or_fail:
    def get(self, _model: Any, _entity_id: Any) -> Any:
        return self._get_result

    # first_or_create / paginate:
    def execute(self, _statement: Any) -> _FakeResult:
        return _FakeResult(first=self._first_result, rows=self._all_result)

    def add(self, entity: Any) -> None:
        self.added.append(entity)

    def flush(self) -> None:
        self.flushed += 1


def _install(monkeypatch: MonkeyPatch, session: _FakeSession) -> None:
    monkeypatch.setattr(tx, "SessionLocal", lambda *_a, **_k: session)


def test_find_or_fail_returns_entity_when_found(monkeypatch: MonkeyPatch) -> None:
    widget = _Widget(id=7)
    _install(monkeypatch, _FakeSession(get_result=widget))

    assert _WidgetRepository().find_or_fail(7) is widget


def test_find_or_fail_raises_resource_not_found_when_missing(monkeypatch: MonkeyPatch) -> None:
    _install(monkeypatch, _FakeSession(get_result=None))

    with pytest.raises(ResourceNotFoundError) as exc_info:
        _WidgetRepository().find_or_fail(7)

    error = exc_info.value
    assert error.status_code == 404
    assert error.error_code == "resource_not_found"
    assert error.details == {"model": "_Widget", "id": "7"}


def test_first_or_create_returns_existing_without_creating(monkeypatch: MonkeyPatch) -> None:
    existing = _Widget(id=1, name="acme")
    session = _FakeSession(first_result=existing)
    _install(monkeypatch, session)

    result = _WidgetRepository().first_or_create({"name": "acme"})

    assert result is existing
    assert session.added == []  # no creó nada
    assert session.flushed == 0


def test_first_or_create_creates_with_where_plus_values_when_missing(monkeypatch: MonkeyPatch) -> None:
    session = _FakeSession(first_result=None)
    _install(monkeypatch, session)

    result = _WidgetRepository().first_or_create({"name": "acme"}, {"color": "red"})

    assert isinstance(result, _Widget)
    # La entidad se construyó con where + values fusionados.
    assert result.name == "acme"
    assert result.color == "red"
    assert session.added == [result]
    assert session.flushed == 1


def test_paginate_reports_has_more_and_trims_to_limit(monkeypatch: MonkeyPatch) -> None:
    # paginate pide limit+1; simulamos que la BD devolvió 3 con limit=2 => hay más.
    rows = [_Widget(id=1), _Widget(id=2), _Widget(id=3)]
    _install(monkeypatch, _FakeSession(all_result=rows))

    page = _WidgetRepository().paginate(offset=0, limit=2, order_by=_Widget.id.desc())

    assert len(page.items) == 2  # recortado a limit
    assert page.has_more is True
    assert page.next_offset == 2


def test_paginate_last_page_has_no_more(monkeypatch: MonkeyPatch) -> None:
    rows = [_Widget(id=5), _Widget(id=6)]  # <= limit => última página
    _install(monkeypatch, _FakeSession(all_result=rows))

    page = _WidgetRepository().paginate(offset=4, limit=2, order_by=_Widget.id.desc())

    assert len(page.items) == 2
    assert page.has_more is False
    assert page.next_offset == 6


def test_cursor_encode_decode_roundtrip() -> None:
    for value in (42, "abc", 0):
        assert _decode_cursor(_encode_cursor(value)) == value


def test_cursor_paginate_has_more_and_next_cursor(monkeypatch: MonkeyPatch) -> None:
    rows = [_Widget(id=1), _Widget(id=2), _Widget(id=3)]  # limit+1 => hay más
    _install(monkeypatch, _FakeSession(all_result=rows))

    page = _WidgetRepository().cursor_paginate(limit=2)

    assert isinstance(page, CursorPage)
    assert len(page.items) == 2
    assert page.has_more is True
    assert page.next_cursor is not None
    assert _decode_cursor(page.next_cursor) == 2  # id de la última fila mostrada


def test_cursor_paginate_last_page_has_no_cursor(monkeypatch: MonkeyPatch) -> None:
    rows = [_Widget(id=5), _Widget(id=6)]  # <= limit => última página
    _install(monkeypatch, _FakeSession(all_result=rows))

    page = _WidgetRepository().cursor_paginate(limit=2)

    assert page.has_more is False
    assert page.next_cursor is None
