# Repositorios y transacciones

tequio adopta un modelo de persistencia **estilo Spring Data / JPA**:

- **Repositorios** tipados (`Repository[Model, Id]`) con CRUD heredado — solo queries.
- **Escrituras** en servicios/handlers `@transactional` (commit/rollback automático).
- **Lecturas** con `@auto_session` (funcionan con o sin scope abierto).
- La **sesión es ambiente** (un contextvar), no se inyecta por constructor.

La división de responsabilidades: el Repository **consulta**, el Service/Handler/Job
**orquesta y transacciona**. En tequio quien abre la transacción no es un controller HTTP,
sino un **job, un cron, un handler del Mediator o un seeder** — pero el patrón es idéntico.

## La sesión ambiente

La sesión vive en un contextvar scoped por **task** (la unidad de trabajo de tequio: un
job de Celery, una corrida de cron, un comando de consola), como el `EntityManager`
thread-bound de Spring. **No** es global de proceso. Cuatro primitivos la gobiernan
(`tequio/Core/Database/Transactional.py`):

| Primitivo | Qué hace | Cuándo usarlo |
|-----------|----------|---------------|
| `current_session()` | Devuelve la sesión del scope; **error claro** si no hay. | dentro de un repo/servicio |
| `session_scope()` | Context manager: abre/cierra la sesión; **commits manuales**. | flujos con varios commits (lotes) |
| `@transactional` | Decorador: abre + **commit on success / rollback on exception**. | servicios/handlers de una transacción |
| `@auto_session` | Decorador: usa la sesión si hay; si no, abre una **efímera** (no commitea). | lecturas / queries de repo |

Todos son **join-or-create** (propagación `REQUIRED`): si ya hay sesión en el contextvar
(llamada anidada), la **reutilizan** y **no** la cierran/commitean — eso lo hace quien la
abrió. Esto hace que anidar servicios `@transactional` produzca **una sola** transacción.

`current_session()` lanza un `RuntimeError` claro si lo usas fuera de un scope (en vez de
fallar en silencio): _"No hay sesión activa: envuelve el acceso a datos en session_scope()
o @transactional."_

## Definir un repositorio

El Demo trae el `NoteRepository` (lecturas de notas), que hereda el CRUD del base sin
queries custom — el demo se quedó sin dueño, así que `all()` basta:

```python
# tequio/Modules/Demo/Repositories/NoteRepository.py
from tequio.Core.Database import Repository
from tequio.Models.Note import Note

class NoteRepository(Repository[Note, int]):
    model = Note
```

Cuando SÍ necesitas una query custom (un filtro propio del dominio), la declaras como un
método público y `self.session` te da la sesión ambiente:

```python
from collections.abc import Sequence
from sqlalchemy import select

class NoteRepository(Repository[Note, int]):
    model = Note

    def archived(self) -> Sequence[Note]:
        """Las notas archivadas, más recientes primero."""
        return self.session.execute(
            select(Note).where(Note.archived).order_by(Note.id.desc())
        ).scalars().all()
```

- `model = Note` declara qué entidad gestiona (y tipa el CRUD heredado a `Note` / `int`).
- `self.session` encapsula `current_session()` — úsalo en tus queries custom; no llames
  `current_session()` a mano.
- Las **queries custom** (métodos públicos como `archived`) se envuelven
  **automáticamente** con `@auto_session` (vía `__init_subclass__`): funcionan con o sin
  scope abierto. No pones el decorador a mano.

### CRUD heredado

| Método | Firma | Decorador |
|--------|-------|-----------|
| `get` | `get(entity_id: IdT) -> ModelT \| None` | `@auto_session` |
| `find_or_fail` | `find_or_fail(entity_id: IdT) -> ModelT` (lanza `ResourceNotFoundError` si no existe) | `@auto_session` |
| `all` | `all() -> Sequence[ModelT]` | `@auto_session` |
| `count` | `count(*, where=None) -> int` (COUNT(*) server-side) | `@auto_session` |
| `paginate` | `paginate(*, offset=0, limit=20, order_by=None, where=None) -> Page[ModelT]` | `@auto_session` |
| `cursor_paginate` | `cursor_paginate(*, cursor=None, limit=20, key=None, descending=False, where=None) -> CursorPage[ModelT]` | `@auto_session` |
| `add` | `add(entity: ModelT) -> ModelT` (hace `flush()` para asignar PK) | `@transactional` |
| `first_or_create` | `first_or_create(where: dict, values: dict \| None = None) -> ModelT` | `@transactional` |
| `delete` | `delete(entity: ModelT) -> None` (lógico si hereda `SoftDeleteMixin`) | `@transactional` |

```python
repo = NoteRepository()
note = repo.get(7)                 # abre sesión efímera si no hay scope; None si no existe
note = repo.find_or_fail(7)        # = findOrFail de Eloquent: lanza ResourceNotFoundError si falta
todas = repo.all()                 # filtra borradas lógicas (si el modelo hereda SoftDeleteMixin)

# firstOrCreate: busca por `where`; si no hay, crea con where + values (extras solo-al-crear)
cliente = ClienteRepository().first_or_create({"rfc": "XAXX010101000"}, {"nombre": "Público"})
```

- **`find_or_fail`** evita el `if x is None: raise` repetido: lanza `ResourceNotFoundError`
  (`tequio.Core.Errors`). En tequio **no** hay un handler HTTP que lo convierta en un 404
  — pero sí es un `DomainError`, así que en la consola el borde del CLI lo renderiza limpio
  (mensaje + código, sin traceback), y en un job/cron queda registrado por loguru. Ver
  [Errores de dominio](19-errores.md). El handler `ArchiveNoteHandler` del Demo la usa así.
- **`first_or_create`** es idempotente por `where`: devuelve el existente o crea uno nuevo
  (con su PK ya asignada vía `flush`). Como es `@transactional`, persiste o se une a la tx
  externa.

> Limitación honesta: no derivamos queries del **nombre** del método (el `findByX` de
> Spring). En Python sería frágil. Las queries custom llevan cuerpo explícito.

## Escribir: servicios y handlers `@transactional`

El `NoteService` del Demo crea una nota en **una** transacción (normalizando el texto con
un [Pipeline](17-pipeline.md) antes de persistir):

```python
# tequio/Modules/Demo/Services/NoteService.py
from tequio.Core.Database import current_session, transactional
from tequio.Models.Note import Note

class NoteService:
    @transactional
    def create(self, title: str, body: str) -> dict[str, Any]:
        note = Note(title=title, body=body)
        current_session().add(note)
        current_session().flush()   # asigna PK sin esperar al commit
        return note_dict(note)      # serializa ANTES del commit (evita DetachedInstance)
```

El handler del comando `ArchiveNote` (Mediator) hace lo mismo, pero modificando una
entidad cargada:

```python
# tequio/Modules/Demo/Handlers/ArchiveNoteHandler.py
@handles(ArchiveNote)
class ArchiveNoteHandler:
    @transactional
    def handle(self, command: ArchiveNote) -> dict[str, Any]:
        note = current_session().get(Note, command.note_id)
        if note is None:
            raise ResourceNotFoundError(f"Nota {command.note_id} no existe", details={"id": command.note_id})
        note.archived = True        # cambio tracked; flush+commit al salir
        return note_dict(note)
```

- Cada método `@transactional` abre sesión, commitea al terminar, o hace rollback si lanza.
- Las llamadas a repos dentro (`add`, `get`, queries) **se unen** a esa transacción.
- No necesitas `session.add()` para objetos ya cargados: SQLAlchemy trackea los cambios.

!!! note "Serializa antes del commit"
    Tanto `NoteService.create` como `ArchiveNoteHandler.handle` devuelven un **dict
    serializado antes del commit**. SQLAlchemy expira los objetos al commitear
    (`expire_on_commit`), así que acceder a sus atributos después del scope dispararía
    `DetachedInstanceError`. Serializar dentro del scope evita ese problema (en milpa la
    misma regla aplicaba al convertir la entidad a DTO antes de devolver el JSON).

### Transacciones compuestas (anidadas)

```python
@transactional
def archivar_y_registrar(self, note_id: int) -> None:
    send(ArchiveNote(note_id=note_id))   # @transactional → se une, no commitea aparte
    self._otros.registrar(note_id)       # @transactional → se une
    # UN solo commit al final; si cualquiera lanza → rollback de TODO
```

## Leer fuera de una transacción

Un job o cron que solo **lee** no necesita `@transactional`: `repo.get()` / `repo.all()`
abren una sesión efímera (gracias a `@auto_session`). Es lo que hacen el `ExportNotesJob`
(en `Jobs/ExportNotesJob.py`) y el `DailyDigestCron` (en `Crons/DailyDigestCron.py`) del Demo:

```python
# tequio/Modules/Demo/Jobs/ExportNotesJob.py
@job(name="demo.export_notes", queue="exports")
def export_user_notes() -> dict[str, int]:
    notes = NoteRepository().all()   # sesión efímera, sin scope explícito
    logger.info("demo.export_notes | {n} notas exportadas (en el worker)", n=len(notes))
    return {"exported": len(notes)}
```

```python
# tequio/Modules/Demo/Crons/DailyDigestCron.py
@cron_task(name="demo.daily_digest", schedule=daily_at("08:00"), output="demo_digest")
def daily_digest() -> None:
    total = len(NoteRepository().all())
    logger.info("demo.daily_digest | {n} notas en total (resumen diario)", n=total)
```

Ver [Jobs](12-jobs.md) y [Programación (cron)](14-programacion-cron.md).

## Control manual: `session_scope`

Para flujos con varios checkpoints de commit (procesos por lotes) — un patrón muy de
tequio, donde un job procesa miles de filas y debe persistir por tramos:

```python
from tequio.Core.Database import session_scope

def procesar_lote(ids: list[int]) -> None:
    repo = NoteRepository()
    with session_scope() as session:
        for i, note_id in enumerate(ids):
            note = repo.get(note_id)            # se une al scope
            if note:
                note.archived = True
            if (i + 1) % 100 == 0:
                session.commit()                # checkpoint cada 100
        session.commit()                        # final
```

Aquí los commits son tuyos (a diferencia de `@transactional`). Es el patrón para preservar
invariantes "persiste el paso N antes de empezar el N+1".

## Paginar en worker-side: `Page` y `CursorPage`

El repositorio hereda dos estrategias de paginación. Aunque en milpa alimentaban un
endpoint de scroll infinito, en tequio sirven para **procesar tablas grandes por tramos
sin traerlas enteras a memoria** — un caso típico de un job de ETL o de exportación.
Ninguna hace `COUNT` por página: piden `limit + 1` filas y deducen `has_more`.

- `Page` (offset/limit): `items`, `has_more`, `next_offset`.
- `CursorPage` (keyset/seek, estable ante inserts concurrentes): `items`, `has_more`,
  `next_cursor` (marcador opaco base64).

```python
# Recorrer TODAS las notas en tramos de 500, sin cargarlas todas de una
repo = NoteRepository()
cursor: str | None = None
while True:
    page = repo.cursor_paginate(cursor=cursor, limit=500)
    for note in page.items:
        ...  # procesar
    if not page.has_more:
        break
    cursor = page.next_cursor
```

El detalle de `paginate` vs `cursor_paginate` (y cómo combinarlos con filtros) está en
[Filtrado y paginación](11-filtrado-y-paginacion.md).

## N+1 y `DetachedInstanceError`

El error clásico: leer una entidad, cerrar la sesión, y luego acceder a una relación lazy →
`DetachedInstanceError`. Dos defensas:

1. **Eager load** dentro del scope con `selectinload`:

   ```python
   def get_con_items(self, invoice_id: int) -> Invoice | None:
       return self.session.execute(
           select(Invoice).where(Invoice.id == invoice_id)
           .options(selectinload(Invoice.items))
       ).scalars().first()
   ```

2. **Devolver un DTO/dict** (no la entidad): serializa todo lo que necesitas mientras la
   sesión está abierta, y deja que la entidad muera con el scope (es lo que hace `note_dict`
   en el Demo).

## Resumen del flujo

```
Job / Cron / Handler / Seeder
  → Service (@transactional: abre sesión, commitea/rollback)
      → Repository (get/add/query: se une a la transacción)
          → SQLAlchemy (SessionLocal sobre el engine; zona fijada por conexión)
  → serializa a dict/DTO (dentro del scope) → resultado del job / log
```

## Siguiente paso

[Filtrado y paginación](11-filtrado-y-paginacion.md).
