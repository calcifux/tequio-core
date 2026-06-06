"""Borrado lógico DECLARATIVO (estilo `SoftDeletes` de Laravel / `@SoftDelete`
de JPA) vía la librería `sqlalchemy-easy-softdelete`.

SQLAlchemy NO trae soft-delete nativo (el mantenedor lo rechazó); el recipe
oficial es un event `do_orm_execute` a mano. Esta librería empaqueta ese recipe
de forma declarativa: generamos un mixin y listo.

- Auto-filtra `deleted_at IS NULL` en TODO SELECT, incluidas las relaciones.
- Columna por default: `deleted_at` (coincide con la BD legacy).
- Instancia: `obj.delete()` marca borrado lógico; `obj.undelete()` lo revierte.
  (OJO: `session.delete(obj)` sigue siendo borrado físico — usar `obj.delete()`.)
- Escape hatch (como withTrashed): `execution_options(include_deleted=True)`.

Los modelos heredan así:  class Invoice(SoftDeleteMixin, Base): ...
"""

from __future__ import annotations

from sqlalchemy_easy_softdelete.mixin import generate_soft_delete_mixin_class


# OPT-IN por modelo: solo hereda este mixin un modelo cuya tabla TIENE deleted_at.
# Los catálogos sin deleted_at NO lo heredan (class X(Base)) y la librería no los toca.
class SoftDeleteMixin(generate_soft_delete_mixin_class()):  # type: ignore[misc]  # base dinámica
    pass
