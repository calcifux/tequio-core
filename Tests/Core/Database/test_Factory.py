"""Tests del Factory base (make / make_many / create / count), SIN BD.

`make`/`make_many` no tocan sesión. `create`/`count` persisten en la sesión AMBIENTE: se
monkeypatchea `SessionLocal` con un fake y se abre un `session_scope` (mismo patrón que el resto).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from pytest import MonkeyPatch
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import tequio.Core.Database.Transactional as tx
from tequio.Core.Database import Factory


class _TestBase(DeclarativeBase):
    pass


class _Gadget(_TestBase):
    __tablename__ = "_gadgets_test"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(default="")
    color: Mapped[str] = mapped_column(default="")


class _GadgetFactory(Factory[_Gadget]):
    model = _Gadget

    def definition(self) -> dict[str, Any]:
        return {"name": "gadget", "color": "blue"}


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flushed = 0

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...

    def add(self, entity: Any) -> None:
        self.added.append(entity)

    def add_all(self, entities: Any) -> None:
        self.added.extend(entities)

    def flush(self) -> None:
        self.flushed += 1


@pytest.fixture
def fake_session(monkeypatch: MonkeyPatch) -> Iterator[_FakeSession]:
    session = _FakeSession()
    monkeypatch.setattr(tx, "SessionLocal", lambda *_a, **_k: session)
    yield session


def test_make_builds_from_definition_and_overrides() -> None:
    gadget = _GadgetFactory().make(color="red")
    assert isinstance(gadget, _Gadget)
    assert gadget.name == "gadget"  # de definition()
    assert gadget.color == "red"  # override


def test_make_many_builds_n() -> None:
    gadgets = _GadgetFactory().make_many(3, color="green")
    assert len(gadgets) == 3
    assert all(g.color == "green" for g in gadgets)


def test_create_persists_in_ambient_session(fake_session: _FakeSession) -> None:
    with tx.session_scope():
        gadget = _GadgetFactory().create(name="x")
    assert fake_session.added == [gadget]
    assert fake_session.flushed == 1
    assert gadget.name == "x"


def test_count_persists_n(fake_session: _FakeSession) -> None:
    with tx.session_scope():
        gadgets = _GadgetFactory().count(5)
    assert len(gadgets) == 5
    assert fake_session.added == gadgets
