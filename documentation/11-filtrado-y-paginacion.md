# Filtrado y paginación

Dos piezas que casi siempre van juntas al recorrer un listado: **filtrar** (qué filas) y
**paginar** (cuántas, en qué tramo). tequio las separa en dos primitivos componibles:

- `FilterQueryModel` — un modelo **Pydantic** que compila un conjunto de criterios
  (búsqueda, orden, igualdades por columna) a condiciones SQLAlchemy.
- `Repository.paginate` / `cursor_paginate` / `count` — los métodos de paginación
  heredados del [Repository](10-repositorios-y-transacciones.md).

El filtro produce `where()` + `order_by()`; el repositorio los consume. Ninguno conoce al
otro: el `FilterQueryModel` es **Pydantic puro + SQLAlchemy**, y el repositorio acepta
cualquier condición.

!!! note "En milpa esto alimentaba la API HTTP; en tequio, tus queries"
    En milpa, `FilterQueryModel` se declaraba como un parámetro `Query()` de FastAPI y
    parseaba los query-params de un `GET /notes?search=...&ordering=-id`. tequio **no tiene
    capa HTTP** (eso vive en [milpa](https://github.com/calcifux/milpa)). Aquí el mismo modelo
    sirve para construir filtros **dentro de un job, un cron, un handler o un seeder**: lo
    construyes en código (no del query-string) y lo pasas a `paginate`/`apply`. La clase es
    la misma — solo cambia de dónde vienen los valores.

## El problema: el `if criterio:` escrito a mano

Sin esto, cada job arma el `where` a mano:

```python
from sqlalchemy import and_
from tequio.Models.Note import Note

def notas(archived: bool, texto: str = "") -> ...:
    where = Note.archived == archived
    if texto:
        where = and_(where, Note.title.ilike(f"%{texto}%"))
    return NoteRepository().paginate(limit=20, order_by=Note.id.desc(), where=where)
```

Funciona, pero el `if texto:` se repite en cada lugar, ordenar por una columna recibida de
fuera (un parámetro de configuración, un mensaje de cola) te obliga a un `match`/`if`
frágil, y es fácil **olvidar** validar el campo de orden (y abrir un `ORDER BY` arbitrario).
El `FilterQueryModel` empaqueta ese patrón.

## `FilterQueryModel` — el filtro declarativo

Subclasea `FilterQueryModel` (`tequio/Core/Database/Filtering.py`), fija el modelo objetivo
en `sa_model` y declara los campos por los que se filtra:

```python
from tequio.Core.Database import FilterQueryModel
from tequio.Models.Note import Note

class NoteFilter(FilterQueryModel):
    sa_model = Note                      # modelo SQLAlchemy objetivo
    search_fields = ("title", "body")    # search -> ILIKE OR sobre estas columnas
    order_fields = ("id", "title")       # ordering="-title" -> ORDER BY (whitelist)

    archived: bool | None = None         # archived=True -> WHERE archived = true (igualdad)
```

`sa_model`, `search_fields` y `order_fields` son **config de clase** (`ClassVar`), no
campos Pydantic. Lo que declares como atributo Pydantic (`archived` arriba) **sí** es un
filtro.

### Las tres partes

| Parte | Atributo | Semántica |
|-------|----------|-----------|
| Campos declarados (`archived`, …) | `archived=True` | **Igualdad exacta** por columna (`columna == valor`). |
| `search` (reservado) | `search="hola"` | `ILIKE '%hola%'` **OR** sobre todas las `search_fields`. |
| `ordering` (reservado) | `ordering="-title"` | `ORDER BY`; prefijo `-` = `DESC`. Solo campos de `order_fields`. |

Decisión KISS y **predecible**: cada campo declarado presente es igualdad exacta; para
texto parcial existe `search` (no se mezclan los dos modos). `search` y `ordering` son
nombres **reservados** del motor del DSL — no los declares como filtros.

Como es Pydantic, lo construyes con keyword-args en tu código worker-side:

```python
NoteFilter(archived=True)                       # solo notas archivadas
NoteFilter(search="factura")                    # busca "factura" en title/body
NoteFilter(archived=True, ordering="-id")       # archivadas, más recientes primero
```

## Compilar a SQLAlchemy: `where()` / `order_by()` / `apply()`

El filtro expone tres métodos. Los dos primeros producen lo que `paginate` espera; el
tercero los aplica a un `select(...)` propio.

### `where() -> condición | None`

AND de los filtros por-campo presentes + la búsqueda. Devuelve `None` si no se pidió
**ningún** filtro, para pasarlo tal cual a `paginate(where=...)`:

```python
NoteFilter().where()                            # -> None (sin filtros)
NoteFilter(archived=True).where()               # -> Note.archived == True
NoteFilter(search="hola").where()               # -> Note.title ILIKE '%hola%' OR Note.body ILIKE '%hola%'
NoteFilter(archived=True, search="hola").where() # -> (archived == True) AND (title ILIKE ... OR body ILIKE ...)
```

### `order_by() -> cláusula | None`

Lee `ordering`; `None` si no se pidió. Prefijo `-` = `DESC`, sin prefijo = `ASC`:

```python
NoteFilter(ordering="title").order_by()   # -> Note.title.asc()
NoteFilter(ordering="-title").order_by()  # -> Note.title.desc()
```

### `apply(statement) -> statement`

Para queries **custom** fuera del repositorio: encadena `where()` + `order_by()` sobre un
`select(...)` y devuelve el statement. Útil dentro de un método de repo o de un job que
arma su propio `select`:

```python
from sqlalchemy import select

stmt = NoteFilter(archived=True, ordering="-id").apply(select(Note))
# -> select(Note).where(Note.archived == True).order_by(Note.id.desc())
rows = current_session().execute(stmt).scalars().all()
```

## El estilo milpa: el filtro como entrada del job

En un job o cron, recibe los criterios como parámetros (de la cola, de la config, de un
mensaje) y construye el filtro una vez. El cuerpo queda sin un solo `if`:

```python
from tequio.Core.Jobs import job
from tequio.Models.Note import Note
from tequio.Modules.Demo.Repositories.NoteRepository import NoteRepository

@job(name="demo.export_filtered", queue="exports")
def export_filtered(archived: bool = False, search: str = "") -> dict[str, int]:
    filters = NoteFilter(archived=archived, search=search or None)
    page = NoteRepository().paginate(
        limit=500,
        where=filters.where(),
        order_by=filters.order_by() or Note.id.desc(),   # fallback a orden estable
    )
    return {"archived": archived, "exported": len(page.items)}
```

Es el equivalente al trío de DRF (`DjangoFilterBackend` + `SearchFilter` + `OrderingFilter`),
pero como **un** modelo Pydantic, y sin acoplarse a ninguna capa HTTP.

> **Nota:** pásale siempre un `order_by` (aunque no haya `ordering`). Sin orden explícito,
> el `offset/limit` no es determinista — ver "orden estable" abajo.

## Nunca falla en silencio: ordering inválido → `InvalidFilterError`

Si pides un `ordering` **fuera** de `order_fields`, `order_by()` **no lo ignora**: lanza
`InvalidFilterError` (`tequio.Core.Errors`):

```python
NoteFilter(ordering="password").order_by()   # order_fields = ("id", "title")
# raise InvalidFilterError("No se puede ordenar por 'password'.",
#                          details={"field": "password", "allowed": ["id", "title"]})
```

`InvalidFilterError` es un `DomainError`: lleva un `error_code` y `details` (con la lista de
columnas permitidas). En milpa, el handler HTTP lo traducía a un sobre **RFC 9457** con
status `422`; en tequio **no hay** esa traducción HTTP — pero el error sigue siendo
explícito y observable: en la consola el borde del CLI lo renderiza limpio (mensaje +
código, sin traceback), y dentro de un job/cron queda registrado por loguru con su
`details`. Ver [Errores de dominio](19-errores.md).

Por qué no ignorarlo: tragarse el parámetro deja al que pidió el orden **creyendo** que
ordenó cuando no pasó nada (un bug silencioso), y un `ORDER BY` abierto a cualquier columna
es una fuga. La whitelist `order_fields` es la **única** lista de columnas ordenables, y el
`details` te devuelve esa lista para que te corrijas. Es el tenet de tequio: **nunca falla
en silencio**.

## Paginar: offset vs. cursor

El repositorio trae dos estrategias. Ninguna hace `COUNT` por página: ambas piden
`limit + 1` filas y deducen `has_more` (más barato que contar el total).

### `paginate` — por offset

```python
def paginate(self, *, offset=0, limit=20, order_by=None, where=None) -> Page[Model]: ...
```

Salta `offset` filas y trae `limit`. Devuelve un `Page` (frozen dataclass):

| Campo | Tipo | Para qué |
|-------|------|----------|
| `items` | `Sequence[Model]` | Las filas de esta página. |
| `has_more` | `bool` | ¿Hay más? (dedujo pidiendo `limit + 1`). |
| `next_offset` | `int` | El `offset` de la siguiente página. |

```python
page = NoteRepository().paginate(offset=0, limit=6, order_by=Note.id.desc(), where=Note.archived == True)
page.items        # hasta 6 notas
page.has_more     # True si hay una 7.ª
page.next_offset  # 6  -> siguiente llamada: offset=6
```

### `cursor_paginate` — por cursor (keyset/seek)

```python
def cursor_paginate(self, *, cursor=None, limit=20, key=None, descending=False, where=None) -> CursorPage[Model]: ...
```

Avanza con un **marcador opaco** (base64) de la última fila en vez de un offset numérico.
`key` debe ser una columna **única y estable** (default: la PK `id`). Devuelve un
`CursorPage`:

| Campo | Tipo | Para qué |
|-------|------|----------|
| `items` | `Sequence[Model]` | Las filas de esta página. |
| `has_more` | `bool` | ¿Hay más? |
| `next_cursor` | `str \| None` | Marcador para la siguiente página; `None` = no hay más. |

```python
first = NoteRepository().cursor_paginate(limit=6, descending=True)
if first.next_cursor:
    nxt = NoteRepository().cursor_paginate(cursor=first.next_cursor, limit=6, descending=True)
```

Es el equivalente al `CursorPagination` de DRF.

### Cuál elegir

| | `paginate` (offset) | `cursor_paginate` (keyset) |
|---|---|---|
| Marcador | `next_offset` (número) | `next_cursor` (opaco) |
| Saltar a la "página N" | Sí | No (solo siguiente/anterior) |
| Costo a profundidad | El motor escanea `offset` filas (caro al fondo) | O(1) (no escanea: filtra por la llave) |
| Inserts concurrentes | **Salta/duplica** filas si insertan arriba | **Estable**: no salta ni duplica |
| Para | Recorridos modestos, tramos numerados | Recorrer tablas grandes / con escrituras concurrentes |

Regla práctica en tequio: un job de **un solo paso** sobre una tabla modesta → `paginate`;
un ETL que **recorre una tabla grande** o que corre mientras hay inserts → `cursor_paginate`
(no se salta filas).

## Orden estable: no pagines sin `order_by`

El `offset/limit` solo es determinista si las filas tienen un **orden total**. Sin
`order_by`, el motor puede devolverlas en cualquier orden y la "página 2" puede repetir o
saltarse filas de la 1. Pasa siempre un orden estable (típicamente la PK):

```python
NoteRepository().paginate(offset=0, limit=20, order_by=Note.id.desc())   # estable
```

`cursor_paginate` lo resuelve por construcción: ordena por su columna-llave única. Si
necesitas ordenar por una columna **no única** (p. ej. `created_at`), ordena por una llave
compuesta que **incluya** la PK como desempate.

## `count()` — el total server-side

Cuando necesitas el **total** (un número en un log de resumen, una métrica), no traigas
todas las filas para contarlas. `count()` emite un `COUNT(*)` server-side:

```python
def count(self, *, where=None) -> int: ...
```

```python
# Forma tradicional (mal): hidrata TODAS las filas a memoria solo para len()
total = len(NoteRepository().all())

# Estilo milpa: COUNT(*) en el servidor, sin hidratar ORM
total = NoteRepository().count(where=Note.archived == True)
```

`count()` acepta el mismo `where` que `paginate`, así que puedes reusar `filters.where()`:

```python
total = NoteRepository().count(where=filters.where())
page = NoteRepository().paginate(where=filters.where(), order_by=filters.order_by() or Note.id.desc())
```

(El `DailyDigestCron` del Demo cuenta notas para su resumen — hoy con `len(all())` por
simplicidad del ejemplo; en un caso real con muchas filas, `count()` es lo correcto.)

## Resumen

- `FilterQueryModel` compila criterios a SQLAlchemy: `search` (ILIKE OR), `ordering`
  (whitelist), campos declarados (igualdad). Expone `where()`, `order_by()`, `apply()`. En
  tequio lo construyes en código (no de query-params HTTP).
- `ordering` fuera de `order_fields` lanza `InvalidFilterError` (un `DomainError`
  observable); **nunca se ignora en silencio**.
- `paginate` (offset) y `cursor_paginate` (keyset, estable) no hacen `COUNT`; para el total
  usa `count()` (server-side, no `len(all())`).
- Pagina **siempre** con un `order_by` estable.

## Siguiente paso

[Jobs (@job)](12-jobs.md).
