# Modelos

Los modelos son clases SQLAlchemy 2.0 que heredan de `Base`. Viven en `app/Models/`
(compartidos por todos los módulos), un modelo por archivo, estilo Eloquent. En el repo
del propio framework viven en `tequio/Models/` (p. ej. el `Note` del Demo).

## Definir un modelo

```python
# app/Models/Invoice.py
from decimal import Decimal
from sqlalchemy import String, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from tequio.Core.Database import Base, TimestampMixin, SoftDeleteMixin

class Invoice(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
```

`Base` (de `tequio.Core.Database`) es la `DeclarativeBase` del proyecto. Trae una
`naming_convention` estable para índices/constraints (migraciones Alembic reproducibles).

## El modelo del Demo: `Note`

El módulo Demo (que copia `tequio new --demo`) define un modelo `Note` **deliberadamente
mínimo**: un título, un cuerpo y una bandera de archivado. Es la base de los ejemplos de
jobs, crons, observers, Mediator y Pipeline:

```python
# tequio/Models/Note.py
from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from tequio.Core.Database import Base, TimestampMixin

class Note(TimestampMixin, Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(default="")
    body: Mapped[str] = mapped_column(default="")
    archived: Mapped[bool] = mapped_column(default=False)
```

!!! note "Un demo a propósito mínimo: `title` / `body` / `archived`"
    El `Note` del demo no carga ningún rastro de usuario. En milpa la nota tenía un dueño
    (`owner_id`, FK a `users` con autorización ABAC), pero tequio es **worker-side y no
    incluye Auth ni la tabla `users`** (eso vive en [milpa](https://github.com/calcifux/milpa)).
    En vez de arrastrar una columna huérfana, el demo se quedó con lo esencial:
    `title`, `body` y `archived` (+ los timestamps del mixin). La columna `archived` la
    alterna el comando `ArchiveNote` vía el [Mediator](16-mediator.md).

    Lo mismo se ve en la migración del Demo (`migrations/versions/b1f4notes01_notes.py`):
    solo `id`, `title`, `body`, `archived` y los timestamps — sin `owner_id` ni su índice.

## Auto-discovery

El paquete de modelos (`app/Models/__init__.py`, o `tequio/Models/__init__.py` en el repo)
importa **todos** los modelos de la carpeta al cargarse (`pkgutil`). Esto es necesario
porque SQLAlchemy debe tener registrados todos los modelos para resolver las relaciones
declaradas por string (`Company` → `CompanyAddress`) sin depender del orden de imports.

Consecuencia práctica: **agregar un modelo = crear su archivo**. No editas el `__init__`.
Y `from app.Models.Invoice import Invoice` basta para que todo el registro quede cargado.

Ese mismo paquete es el que `import_all_models()` (Registry) importa antes del autogenerate
de Alembic y antes de los seeders: así `Base.metadata` está completa sin una lista manual.
Dónde escanear se configura con `MODELS_PACKAGE` (default `tequio.Models`; un proyecto
externo lo apunta a `app.Models`). Ver [Configuración](03-configuracion.md).

(Contrasta con `app/Dictionaries`, que son constantes y no necesitan registro: se importan
por submódulo. Ver [Estructura](04-estructura-directorios.md).)

## Mixins: timestamps y soft delete

Ambos son **opt-in por modelo**: solo los hereda un modelo cuya tabla tiene las columnas.

### `TimestampMixin`

Agrega dos columnas que la **BD** llena (server-side, en la zona de la app):

| Columna | Comportamiento |
|---------|----------------|
| `created_at` | se setea al INSERT (`func.now()`). |
| `updated_at` | se setea al INSERT y se refresca en cada UPDATE (= `$table->timestamps()`). |

```python
class Invoice(TimestampMixin, Base):
    ...
```

El `Note` del Demo lo hereda, así cada nota lleva `created_at`/`updated_at` sin código
extra.

> En SQLite (default y tests) no hay zona por sesión → `func.now()` cae a UTC. En prod
> (Postgres/MySQL) sale en hora local. Ver [Base de datos](08-base-de-datos.md).

### `SoftDeleteMixin`

Borrado lógico (vía `sqlalchemy-easy-softdelete`). Agrega `deleted_at` y:

- **Filtra automáticamente** `deleted_at IS NULL` en todo SELECT (incluidas relaciones).
- Marca como borrado en vez de eliminar físicamente: `obj.delete()` (lógico) /
  `obj.undelete()` (revierte). Ojo: `session.delete(obj)` sigue siendo borrado **físico**.

```python
class Invoice(TimestampMixin, SoftDeleteMixin, Base):
    ...
```

Para **incluir** borrados lógicos en una query puntual (= `withTrashed` de Laravel) — útil
en un job de purga o de auditoría que sí debe ver lo borrado:

```python
session.execute(
    select(Invoice).execution_options(include_deleted=True)
).scalars().all()
```

Los catálogos sin estas columnas simplemente no heredan los mixins:

```python
class Moneda(Base):                       # sin timestamps ni soft delete
    __tablename__ = "monedas"
    codigo: Mapped[str] = mapped_column(String(3), primary_key=True)
```

(El `Note` del Demo **no** hereda `SoftDeleteMixin`: usa una columna `archived` booleana
propia para el archivado, que alterna el comando `ArchiveNote` vía el
[Mediator](16-mediator.md).)

## Relaciones

Relaciones SQLAlchemy normales. Como todos los modelos se auto-importan, puedes declararlas
por string sin preocuparte del orden:

```python
from sqlalchemy.orm import relationship, Mapped

class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    items: Mapped[list["InvoiceItem"]] = relationship(back_populates="invoice")
```

Para leer grafos de objetos sin caer en N+1 ni en `DetachedInstanceError`, usa eager
loading (`selectinload`) dentro del scope de sesión y devuelve un DTO. Ver
[Repositorios y transacciones](10-repositorios-y-transacciones.md).

## Poblar para pruebas: factories y seeders

Para datos de ejemplo/volumen, el Demo usa una **Factory** (Faker) y un **Seeder**. La
factory fija `model` y un `definition()`:

```python
# tequio/Modules/Demo/Factories/factories.py
from tequio.Core.Database import Factory
from tequio.Core.Database.Faker import faker
from tequio.Models.Note import Note

class NoteFactory(Factory[Note]):
    model = Note
    def definition(self) -> dict[str, Any]:
        return {
            "title": faker.sentence(nb_words=4).rstrip("."),
            "body": faker.paragraph(nb_sentences=2),
        }
```

El locale de Faker es configurable (`FAKER_LOCALE` en `.env`; default `es_MX`). El seeder
la usa (y mezcla un dato a mano):

```python
# tequio/Modules/Demo/Seeders/DemoSeeder.py
class DemoSeeder(Seeder):
    def run(self) -> None:
        if current_session().execute(select(Note).limit(1)).first() is not None:
            return  # idempotente: ya sembrado
        NoteFactory().count(23)   # 23 notas con Faker
        NoteFactory().create(title="Idea de Beto", body="Probar tequio este finde")
```

`python jornal db seed` descubre y corre los seeders. Ver
[La consola jornal](07-consola-jornal.md).

## Siguiente paso

[Repositorios y transacciones](10-repositorios-y-transacciones.md).
