# Mediator (command bus)

El **Mediator** de tequio es un *command bus* **1:1**: mapea un TIPO de comando a UN
handler y delega. Un comando es una **intención** que tú envías explícitamente con
`send(...)` y de la que **esperas un resultado**. Es el patrón con el que sacas un caso de
uso de un sitio para reusarlo **transport-neutral**: el MISMO `send(...)` corre desde
la CLI, desde un Job o desde un service, sin duplicar la lógica.

```python
from tequio.Core.Mediator import send
from tequio.Modules.Demo.Commands import ArchiveNote

result = send(ArchiveNote(note_id=7))
```

Es un patrón **opt-in del estilo milpa**: nadie te obliga a usarlo. Si tu código solo va a
llamar a un service, llama al service — no metas un comando de adorno. El Mediator gana su
lugar cuando **el mismo caso de uso entra por más de un transporte**.

!!! note "En milpa el primer transporte era HTTP"
    En milpa, el caso de uso "archivar nota" entraba por un endpoint `POST /notes/{id}/archive`
    **y** por la CLI con el mismo `send(...)`. tequio es **worker-side**: no tiene capa HTTP
    (eso vive en [milpa](https://github.com/calcifux/milpa)). Aquí el valor es el mismo, pero los
    transportes son la **CLI**, los **jobs** y los **services**.

## Las tres piezas

| Pieza | Qué es | Dónde vive |
|-------|--------|------------|
| **Comando** | Un dataclass con los datos de la intención (solo datos, sin lógica). | `Modules/<X>/Commands.py` |
| **Handler** | Una clase con `.handle(command)` que ejecuta el caso de uso y **devuelve** algo. | en el árbol del módulo (el demo: `Handlers/ArchiveNoteHandler.py`) |
| **`send(command)`** | La facade: busca el handler del tipo y lo ejecuta, devolviendo su resultado. | `tequio.Core.Mediator` |

### El comando: solo datos

Un comando es un `@dataclass` que describe **qué** quieres hacer, no **cómo**. Del módulo
`Demo` (`Modules/Demo/Commands.py`):

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ArchiveNote:
    """Archivar una nota."""

    note_id: int
```

No tiene métodos ni dependencias: es el sobre que viaja al handler.

### El handler: una clase con `.handle()`

Un handler es **cualquier clase con un método `.handle(command)`** — no hay base genérica
que heredar. Lo marcas con `@handles(Comando)` y, al importarse, se auto-registra. Del
módulo `Demo` (`Modules/Demo/Handlers/ArchiveNoteHandler.py`):

```python
from __future__ import annotations

from typing import Any

from tequio.Core.Database import current_session, transactional
from tequio.Core.Errors import ResourceNotFoundError
from tequio.Core.Mediator import handles
from tequio.Models.Note import Note
from tequio.Modules.Demo.Commands import ArchiveNote
from tequio.Modules.Demo.Services.NoteService import note_dict


@handles(ArchiveNote)
class ArchiveNoteHandler:
    """Marca `archived=True` en la nota."""

    @transactional
    def handle(self, command: ArchiveNote) -> dict[str, Any]:
        note = current_session().get(Note, command.note_id)
        if note is None:
            raise ResourceNotFoundError(f"Nota {command.note_id} no existe", details={"id": command.note_id})
        note.archived = True
        return note_dict(note)
```

El handler concentra el caso de uso completo: carga el recurso y muta. Devuelve el dict
serializado **antes** del commit, así evita el objeto *detached* del `expire_on_commit`.

!!! note "Aquí en milpa había autorización (Gate / ABAC)"
    El handler de milpa cargaba al actor y llamaba `Gate.authorize("note.update", note,
    user=actor)` (dueño o moderador) antes de mutar. tequio **no tiene Auth** (eso vive en
    [milpa](https://github.com/calcifux/milpa)): el demo se quedó **sin dueño ni actor**, así que
    el comando `ArchiveNote` solo lleva el `note_id` y no hay chequeo de permisos. Por eso
    tampoco importa policies en la CLI (ver más abajo).

### `send(command)`: enviar y recibir

```python
from tequio.Core.Mediator import send

send(command: object) -> Any
```

`send` busca el handler registrado para `type(command)`, lo instancia y llama a su
`.handle(command)`, **devolviendo el resultado**. Es **síncrono**. Se llama `send` (no
`dispatch`) a propósito: marca que aquí **envías** una intención 1:1 y **esperas
retorno**, a diferencia de los eventos.

## El decorador `@handles`

```python
from tequio.Core.Mediator import handles

@handles(ArchiveNote)
class ArchiveNoteHandler:
    def handle(self, command: ArchiveNote) -> dict[str, Any]: ...
```

`@handles(Comando)` registra el mapeo `Comando -> Handler` en el momento en que el módulo
del handler se importa. El registro es **1:1**: un comando, un handler. No hay
multi-handler, pipelines ni *behaviors* — eso sería un MediatR completo (un framework
dentro del framework), y tequio lo deja fuera a propósito (KISS).

## Caso de uso transport-neutral: el MISMO `send`

Aquí está el corazón del patrón. El caso de uso "archivar nota" vive en **un solo lugar**
(el handler) y se invoca con la **misma** línea `send(ArchiveNote(...))` desde cualquier
transporte worker-side.

### Desde la CLI

El command `demo archive <note_id>`
(`Modules/Demo/Console/Commands/ArchiveNoteCommand.py`) **no reimplementa nada**: envía el
mismo comando.

```python
from __future__ import annotations

import typer

from tequio.Core.Console import console_command
from tequio.Core.Mediator import send
from tequio.Core.Registry import import_all_handlers
from tequio.Modules.Demo.Commands import ArchiveNote


@console_command(name="archive", help="Archiva una nota (vía Mediator; mismo comando que usaría un Job/servicio).")
def archive_note(note_id: int) -> None:
    """Envía el comando ArchiveNote y reporta el resultado."""
    # La CLI no corre el lifespan: registra a mano lo que el caso de uso necesita.
    import_all_handlers()  # handlers del Mediator (resuelve ArchiveNote -> ArchiveNoteHandler)
    result = send(ArchiveNote(note_id=note_id))
    typer.echo(f"Nota {result['id']} archivada (archived={result['archived']}).")
```

```bash
tequio demo archive 7
# Nota 7 archivada (archived=True).
```

### Desde un Job o un service

El **mismo** `send(ArchiveNote(...))` corre dentro de un [job](12-jobs.md) de background o de
otro service, sin copiar nada. Cambia el efecto de archivar **una vez**, en el handler, y todos
los transportes quedan al día. Eso es lo que el command bus compra.

### Los procesos sueltos deben correr el discovery a mano

Detalle importante: un proceso que **no pasa por el arranque normal** (la CLI, un script) debe
importar los handlers explícitamente **antes** de enviar:

```python
from tequio.Core.Registry import import_all_handlers

import_all_handlers()  # registra los @handles(...) → sin esto, HandlerNotFoundError
```

`import_all_handlers()` importa **todo el árbol** de cada módulo para que los `@handles(...)`
se registren (es lo que `send` consulta). Sin esa llamada, `send` no encuentra el handler.

!!! note "tequio NO importa policies"
    En milpa, la CLI llamaba también a `import_all_policies()` porque el handler autorizaba con
    el Gate. tequio no tiene Auth ni policies, así que solo necesitas `import_all_handlers()`.

## `HandlerNotFoundError`: cuando falta el handler

Si envías un comando sin handler registrado, `send` lanza `HandlerNotFoundError`:

```python
handler_cls = _HANDLERS.get(type(command))
if handler_cls is None:
    raise HandlerNotFoundError(command_type=type(command).__name__)
```

No es un error de cliente: es un **bug de programación** (olvidaste `@handles(MiComando)`,
o el módulo no se descubrió — p. ej. la CLI sin `import_all_handlers()`). Vive en
`tequio.Core.Errors`. Ver [Errores de dominio](19-errores.md).

## Mediator vs. Observer

El Mediator convive con el patrón **Observer** (eventos de dominio), pero resuelven
problemas opuestos. No los confundas:

| | **Mediator** (`send`) | **Observer** (`dispatch`) |
|---|---|---|
| Relación | **1:1** — un comando, un handler | **1:N** — un evento, varios listeners |
| Retorno | **Sí**, `send` devuelve el resultado | **No**, los eventos no devuelven nada |
| Semántica | "Haz esto" (una **intención**) | "Esto pasó" (un **hecho**) |
| Facade | `send(comando)` | `dispatch(evento)` |
| Falta destinatario | `HandlerNotFoundError` (es un bug) | OK: cero listeners es válido |

Regla mental: si **esperas un resultado** y hay **un solo** responsable, es un comando
(`send`). Si solo **anuncias que algo ocurrió** y a varios les puede interesar reaccionar
(sin que tú esperes nada), es un evento (`dispatch`). Ver [Eventos y Observers](15-eventos-y-observers.md).

## Forma tradicional vs. estilo milpa

**Forma tradicional** — la lógica de "archivar" vive en el command de consola y se copia (o
se adapta) cuando la quieres también en un job:

```python
# En el command de consola...
note = repo.find_or_fail(note_id)
note.archived = True
# ...y otra vez, casi igual, dentro de un Job → dos copias que divergen.
```

**Estilo milpa** — el caso de uso vive en un handler y ambos transportes lo **envían**:

```python
result = send(ArchiveNote(note_id=note_id))
```

La transacción y la mutación quedan en **un** sitio (`ArchiveNoteHandler`) y se reusan tal
cual desde la CLI, un Job o un service.

## Introspección y tests

Para inspeccionar o probar el registro tienes dos helpers en `tequio.Core.Mediator`:

```python
from tequio.Core.Mediator import registered_handlers, reset_handlers

registered_handlers()   # dict {Comando: Handler} de lo registrado (introspección + tests)
reset_handlers()        # limpia el registro — SOLO para tests
```

## Siguiente paso

[Pipeline](17-pipeline.md).
