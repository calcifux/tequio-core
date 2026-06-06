"""Tests de la sesión ambiente + session_scope/@transactional, SIN BD.

Usamos un fake de Session que cuenta commit/rollback/close: validamos la LÓGICA
(join-or-create, commit on success, rollback on exception) sin tocar un motor.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest import MonkeyPatch

import tequio.Core.Database.Transactional as tx


class _FakeSession:
    def __init__(self) -> None:
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1

    def close(self) -> None:
        self.closed += 1


def _patch_sessions(monkeypatch: MonkeyPatch) -> list[_FakeSession]:
    """Reemplaza SessionLocal por una fábrica que captura cada sesión creada."""
    created: list[_FakeSession] = []

    def factory(*_a: Any, **_k: Any) -> _FakeSession:
        session = _FakeSession()
        created.append(session)
        return session

    monkeypatch.setattr(tx, "SessionLocal", factory)
    return created


def test_current_session_raises_outside_scope() -> None:
    with pytest.raises(RuntimeError):
        tx.current_session()


def test_session_scope_opens_closes_without_autocommit(monkeypatch: MonkeyPatch) -> None:
    created = _patch_sessions(monkeypatch)
    with tx.session_scope() as session:
        assert tx.current_session() is session  # sesión ambiente disponible dentro
    assert len(created) == 1
    assert created[0].committed == 0  # commits MANUALES: el scope no commitea
    assert created[0].closed == 1
    with pytest.raises(RuntimeError):
        tx.current_session()  # cerrado al salir


def test_transactional_commits_on_success(monkeypatch: MonkeyPatch) -> None:
    created = _patch_sessions(monkeypatch)

    @tx.transactional
    def do() -> str:
        return "ok"

    assert do() == "ok"
    assert created[0].committed == 1 and created[0].rolled_back == 0 and created[0].closed == 1


def test_transactional_rolls_back_and_reraises(monkeypatch: MonkeyPatch) -> None:
    created = _patch_sessions(monkeypatch)

    @tx.transactional
    def boom() -> None:
        raise ValueError("x")

    with pytest.raises(ValueError):
        boom()
    assert created[0].committed == 0 and created[0].rolled_back == 1 and created[0].closed == 1


def test_nested_transactional_joins_outer(monkeypatch: MonkeyPatch) -> None:
    created = _patch_sessions(monkeypatch)

    @tx.transactional
    def inner() -> None:
        pass

    @tx.transactional
    def outer() -> None:
        inner()  # se une a la tx de outer: NO crea sesión nueva ni commitea aparte

    outer()
    assert len(created) == 1  # solo outer creó sesión
    assert created[0].committed == 1 and created[0].closed == 1  # un solo commit/close
