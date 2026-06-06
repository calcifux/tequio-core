"""Sesión AMBIENTE (contextvar) + dos primitivos hermanos.

El modelo es el de Spring/JPA: una sesión "context-bound" que los repos toman con
`current_session()` (sin recibirla por constructor). Dos formas de abrir el scope:

  - `session_scope()` — abre/cierra la sesión ambiente; commits MANUALES. Para
    control-fino (jobs, flujos multi-commit como un proceso por lotes). NO auto-commitea.
  - `@transactional` — `session_scope` + commit on success / rollback on exception.
    Para servicios de UNA transacción. Estilo `@Transactional` de Spring.

Ambos son JOIN-OR-CREATE (propagación REQUIRED): si ya hay una sesión en el contextvar
(llamada anidada), la REUSAN y NO la cierran/commitean — eso lo hace quien la abrió.

Ambiente != global: el contextvar está scoped por request/task (como el EntityManager
thread-bound de Spring), no es una sesión global de proceso.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy.orm import Session

from tequio.Core.Database.Session import SessionLocal

# Sesión del scope actual (request/task). La fijan session_scope()/@transactional.
_session_ctx: ContextVar[Session | None] = ContextVar("db_session", default=None)


def current_session() -> Session:
    """La sesión ambiente del scope actual. Error claro si se usa fuera de un scope."""
    session = _session_ctx.get()
    if session is None:
        raise RuntimeError("No hay sesión activa: envuelve el acceso a datos en session_scope() o @transactional.")
    return session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Abre la sesión ambiente (si no hay) y la cierra al salir. Commits MANUALES.

    Anidado: si ya hay sesión, la REUSA y NO la cierra (la gobierna el scope externo).
    Útil para control-fino: jobs/flujos que commitean por checkpoint (p. ej. un
    proceso por lotes donde cada paso debe persistirse antes de seguir con el siguiente).
    """
    existing = _session_ctx.get()
    if existing is not None:
        yield existing  # join: ya hay scope; no abrir ni cerrar
        return
    session = SessionLocal()
    token = _session_ctx.set(session)
    try:
        yield session
    finally:
        session.close()
        _session_ctx.reset(token)


def transactional[F: Callable[..., Any]](func: F) -> F:
    """Decorador estilo `@Transactional`: scope + commit on success / rollback on error.

    Join-or-create: si ya hay sesión (llamada anidada), se UNE a la transacción de
    afuera y NO commitea aquí (lo hace el método externo). Para servicios de UNA
    transacción; si necesitas multi-commit por checkpoint, usa `session_scope()`.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        existing = _session_ctx.get()
        if existing is not None:
            return func(*args, **kwargs)  # join: no abre, no commitea (lo hace el externo)
        session = SessionLocal()
        token = _session_ctx.set(session)
        try:
            result = func(*args, **kwargs)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            _session_ctx.reset(token)

    return wrapper  # type: ignore[return-value]


def auto_session[F: Callable[..., Any]](func: F) -> F:
    """Asegura una sesión para ESTA llamada, sin que el dev abra un scope (Spring Data).

    Si ya hay sesión ambiente (dentro de @transactional/session_scope), se UNE a ella.
    Si no, abre una EFÍMERA solo para la llamada y la cierra al salir. Pensado para los
    métodos de REPOSITORIO (lecturas): `repo.get(id)` funciona con o sin scope, así el
    dev NUNCA tiene que acordarse de envolver una query. NO commitea (los reads no lo
    necesitan; las escrituras van por @transactional en un service). Agrupar varias ops
    en UNA transacción sigue siendo decisión explícita (session_scope/@transactional).
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _session_ctx.get() is not None:
            return func(*args, **kwargs)  # join: ya hay sesión ambiente
        with session_scope():
            return func(*args, **kwargs)  # efímera solo para esta llamada

    return wrapper  # type: ignore[return-value]
