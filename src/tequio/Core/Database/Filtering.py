"""Filtering DSL declarativo: un `FilterQueryModel` (Pydantic) compila query-params a
condiciones SQLAlchemy (`where`/`order_by`) que alimentan `Repository.paginate` / `cursor_paginate`.

Reemplaza el `if q: where = and_(Note.title.ilike(...))` escrito a mano en cada controller. = el
trío de DRF (DjangoFilterBackend + SearchFilter + OrderingFilter), pero como UN modelo Pydantic:

    class NoteFilter(FilterQueryModel):
        sa_model = Note                      # modelo SQLAlchemy objetivo
        search_fields = ("title", "body")    # ?search= -> ILIKE OR sobre estas columnas
        order_fields = ("id", "title")       # ?ordering=-title -> ORDER BY (whitelist)

        owner_id: int | None = None          # ?owner_id=3 -> WHERE owner_id = 3 (igualdad)

    @Get("/notes")
    def list_notes(self, filters: Annotated[NoteFilter, Query()]) -> ...:
        page = NoteRepository().paginate(where=filters.where(), order_by=filters.order_by())

Semántica (KISS y PREDECIBLE): cada campo declarado presente = igualdad exacta; para texto parcial
usa `search` (ILIKE OR). El `ordering` solo acepta campos de la whitelist `order_fields`: pedir uno
fuera de ella NO se ignora en silencio — lanza `InvalidFilterError` (422) con los permitidos (tenet
"nunca falla en silencio"). Es Pydantic puro + SQLAlchemy: sin acoplar a FastAPI (sirve igual en CLI).
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy import and_, or_

from tequio.Core.Errors import InvalidFilterError

# Campos RESERVADOS del modelo base (no son filtros por-columna, sino el motor del DSL).
_RESERVED_FIELDS = frozenset({"search", "ordering"})


class FilterQueryModel(BaseModel):
    """Base de los filtros declarativos. Subclasea fijando `sa_model` (+ opcional `search_fields`
    / `order_fields`) y declarando los campos por los que se filtra (igualdad). Expone `where()`,
    `order_by()` y `apply(stmt)`."""

    # Config de clase (NO son campos Pydantic): el modelo objetivo y las whitelists.
    sa_model: ClassVar[type[Any]]
    search_fields: ClassVar[tuple[str, ...]] = ()
    order_fields: ClassVar[tuple[str, ...]] = ()

    # Motor del DSL (sí son campos: se parsean del query-string).
    search: str | None = None
    ordering: str | None = None

    def _column(self, name: str) -> Any:
        """La columna SQLAlchemy del `sa_model` por nombre (asume nombre-de-campo == columna)."""
        return getattr(self.sa_model, name)

    def _filter_values(self) -> dict[str, Any]:
        """Campos declarados por la subclase (filtros de igualdad) que vienen con valor."""
        values: dict[str, Any] = {}
        for name in type(self).model_fields:
            if name in _RESERVED_FIELDS:
                continue
            value = getattr(self, name)
            if value is not None:
                values[name] = value
        return values

    def where(self) -> Any | None:
        """Condición SQLAlchemy combinada (AND) de los filtros por-campo + la búsqueda; `None` si
        no se pidió ningún filtro (para pasarla tal cual a `paginate(where=...)`)."""
        conditions: list[Any] = [self._column(name) == value for name, value in self._filter_values().items()]
        if self.search and self.search_fields:
            like = f"%{self.search}%"
            conditions.append(or_(*(self._column(field).ilike(like) for field in self.search_fields)))
        if not conditions:
            return None
        return and_(*conditions) if len(conditions) > 1 else conditions[0]

    def order_by(self) -> Any | None:
        """Cláusula ORDER BY desde `ordering` (prefijo '-' = DESC); `None` si no se pidió orden.
        Si el campo no está en `order_fields`, lanza `InvalidFilterError` (no lo ignora)."""
        if not self.ordering:
            return None
        descending = self.ordering.startswith("-")
        field = self.ordering.lstrip("+-")
        if field not in self.order_fields:
            raise InvalidFilterError(
                f"No se puede ordenar por {field!r}.",
                details={"field": field, "allowed": list(self.order_fields)},
            )
        column = self._column(field)
        return column.desc() if descending else column.asc()

    def apply(self, statement: Any) -> Any:
        """Aplica `where()` + `order_by()` a un `select(...)` (para queries custom fuera del
        Repository). Devuelve el statement encadenado."""
        where = self.where()
        if where is not None:
            statement = statement.where(where)
        order = self.order_by()
        if order is not None:
            statement = statement.order_by(order)
        return statement
