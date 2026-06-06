"""Base de repositorios tipada, estilo `JpaRepository<Model, Id>` de Spring Data.

Heredar de `Repository[Model, Id]` te da:
  - CRUD comun GRATIS y TIPADO: `get(id) -> Model | None`, `all()`, `add()`, `delete()`.
  - `self.session` (la sesion AMBIENTE encapsulada) para las queries CUSTOM, en vez de
    llamar `current_session()` a mano.
  - Auto-gestion de sesion: los metodos publicos son @auto_session (lecturas) — funcionan
    CON o SIN `session_scope`; el dev no envuelve nada. `add`/`delete` son @transactional
    (escriben -> commitean, o se unen a la tx de afuera).

Ejemplo:

    class CompanyRepository(Repository[Company, int]):
        model = Company
        def find_subastador(self) -> Company | None:           # query custom
            return self.session.execute(select(Company).where(...)).scalars().first()

    CompanyRepository().get(7)              # heredado, tipado Company | None, sin scope

LIMITE (honesto): no derivamos queries desde el NOMBRE del metodo (el `findByX` de
Spring Data usa proxies en runtime; en Python seria metaprogramacion fragil). Las
queries custom llevan cuerpo, pero usan `self.session`.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from types import FunctionType
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tequio.Core.Database.Transactional import auto_session, current_session, transactional
from tequio.Core.Errors import ResourceNotFoundError


@dataclass(frozen=True)
class Page[T]:
    """Una página de resultados para paginación / scroll infinito (SIN COUNT total).

    `has_more` se deduce pidiendo `limit + 1` filas (más barato que un `COUNT(*)`), y `next_offset`
    es el offset de la siguiente página — úsalo en el marcador HTMX (`?offset=...`).
    """

    items: Sequence[T]
    has_more: bool
    next_offset: int


@dataclass(frozen=True)
class CursorPage[T]:
    """Página por CURSOR (keyset/seek): `next_cursor` es un marcador OPACO de la última fila.

    A diferencia del offset, NO se salta/duplica filas cuando hay inserts concurrentes y es O(1)
    a cualquier profundidad (no escanea offset filas). = `CursorPagination` de DRF. Pasa
    `next_cursor` como `?cursor=...` para la siguiente página; `None` = no hay más.
    """

    items: Sequence[T]
    has_more: bool
    next_cursor: str | None


def _encode_cursor(value: Any) -> str:
    """Marcador opaco (base64 de JSON) del valor de la columna-llave de la última fila."""
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def _decode_cursor(cursor: str) -> Any:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


class Repository[ModelT, IdT]:
    """Base CRUD tipada por (modelo, tipo de id). La subclase fija `model`."""

    model: type[ModelT]

    @property
    def session(self) -> Session:
        """La sesion AMBIENTE (la abre @auto_session/@transactional). Encapsula
        `current_session()` para que las queries custom no lo llamen directo."""
        return current_session()

    @auto_session
    def get(self, entity_id: IdT) -> ModelT | None:
        return self.session.get(self.model, entity_id)

    @auto_session
    def find_or_fail(self, entity_id: IdT) -> ModelT:
        """Como `get`, pero NUNCA devuelve None: si no existe, lanza `ResourceNotFoundError`
        (= `findOrFail` de Eloquent / `getReferenceById` que falla en Spring Data). El
        handler global la traduce a un 404 JSON; el service no tiene que checar None a mano."""
        entity = self.session.get(self.model, entity_id)
        if entity is None:
            raise ResourceNotFoundError(
                f"{self.model.__name__} con id {entity_id!r} no existe",
                details={"model": self.model.__name__, "id": str(entity_id)},
            )
        return entity

    @auto_session
    def all(self) -> Sequence[ModelT]:
        return self.session.execute(select(self.model)).scalars().all()

    @auto_session
    def count(self, *, where: Any = None) -> int:
        """Cuenta filas con un `COUNT(*)` server-side (O(1) en transferencia, SIN hidratar ORM).
        Úsalo para totales/badges en vez de `len(all())`, que trae todas las filas a memoria."""
        statement = select(func.count()).select_from(self.model)
        if where is not None:
            statement = statement.where(where)
        return int(self.session.execute(statement).scalar_one())

    @auto_session
    def paginate(self, *, offset: int = 0, limit: int = 20, order_by: Any = None, where: Any = None) -> Page[ModelT]:
        """Página por `offset`/`limit` (estilo scroll infinito). Pasa `order_by` para orden
        ESTABLE (p. ej. `Model.id.desc()`) y `where` como condición opcional. No hace COUNT:
        pide `limit + 1` filas y deduce `has_more`."""
        statement = select(self.model)
        if where is not None:
            statement = statement.where(where)
        if order_by is not None:
            statement = statement.order_by(order_by)
        rows = list(self.session.execute(statement.offset(offset).limit(limit + 1)).scalars().all())
        return Page(items=rows[:limit], has_more=len(rows) > limit, next_offset=offset + limit)

    @auto_session
    def cursor_paginate(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
        key: Any = None,
        descending: bool = False,
        where: Any = None,
    ) -> CursorPage[ModelT]:
        """Paginación por CURSOR (keyset/seek). `key` debe ser una columna ÚNICA y estable
        (default: la PK `id`); ordena por ella y avanza con un marcador opaco — sin COUNT, sin
        offset, estable ante inserts concurrentes. = `CursorPagination` de DRF.

        Útil para feeds/listados grandes o en tiempo real. (KISS: una sola columna-llave única;
        para desempates por columnas no únicas, ordena por una llave compuesta que incluya la PK.)
        """
        key_col: Any = key if key is not None else getattr(self.model, "id")  # noqa: B009
        statement = select(self.model)
        if where is not None:
            statement = statement.where(where)
        if cursor is not None:
            last = _decode_cursor(cursor)
            statement = statement.where(key_col < last if descending else key_col > last)
        statement = statement.order_by(key_col.desc() if descending else key_col.asc())
        rows = list(self.session.execute(statement.limit(limit + 1)).scalars().all())
        items = rows[:limit]
        has_more = len(rows) > limit
        next_cursor = _encode_cursor(getattr(items[-1], key_col.key)) if (has_more and items) else None
        return CursorPage(items=items, has_more=has_more, next_cursor=next_cursor)

    @transactional
    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        self.session.flush()  # asigna PK/defaults sin esperar al commit
        return entity

    @transactional
    def delete(self, entity: ModelT) -> None:
        self.session.delete(entity)

    @transactional
    def first_or_create(self, where: dict[str, Any], values: dict[str, Any] | None = None) -> ModelT:
        """Busca la PRIMERA fila que cumpla `where`; si no hay, la CREA con `where + values`
        (= `firstOrCreate` de Eloquent). `where` son las columnas de búsqueda/identidad;
        `values` son extras solo-al-crear. Es @transactional: si crea, persiste (o se une a
        la tx de afuera). Devuelve la entidad existente o la recién creada (con su PK)."""
        existing = self.session.execute(select(self.model).filter_by(**where)).scalars().first()
        if existing is not None:
            return existing
        entity = self.model(**{**where, **(values or {})})
        self.session.add(entity)
        self.session.flush()  # asigna PK/defaults sin esperar al commit
        return entity

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Los metodos CUSTOM (queries) de la subclase: auto_session (con o sin scope).
        # El CRUD heredado ya viene decorado en la base; aqui solo lo propio de la subclase.
        for name, attribute in list(vars(cls).items()):
            if isinstance(attribute, FunctionType) and not name.startswith("_"):
                setattr(cls, name, auto_session(attribute))
