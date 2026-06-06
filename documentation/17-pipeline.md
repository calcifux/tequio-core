# Pipeline

El **Pipeline** pasa UN objeto por una serie de etapas (`pipes`) en orden. Cada etapa
recibe el objeto y un `next`, y decide si **sigue** (llama `next(passable)`) o **corta**
(no lo llama). Es el `Illuminate\Pipeline` de Laravel: el **modelo cebolla** (el mismo de
los middleware), pero como utilidad pura y reusable para tu propia lógica de dominio.

```python
from tequio.Core.Pipeline import Pipeline

resultado = (
    Pipeline()
    .send(objeto)
    .through([PrimeraEtapa(), SegundaEtapa()])
    .then_return()
)
```

A diferencia de los [Events/Observers](15-eventos-y-observers.md) (1:N, *fire-and-forget*)
o el [Mediator](16-mediator.md) (1 intención → 1 handler), aquí **un objeto fluye por
varias etapas** que lo transforman o lo detienen, en un orden que tú controlas.

## Cuándo usarlo

Cuando una operación es en realidad **una secuencia de pasos** sobre el mismo objeto:
normalizar/limpiar datos antes de guardar, una cadena de validaciones, transformaciones
encadenadas, filtros. El valor está en que cada paso es una pieza **componible y
reordenable**, en vez de líneas sueltas amontonadas dentro de un método.

## El contrato: el `Protocol` `Pipe`

Una etapa es cualquier objeto con un método `handle(passable, next)`. tequio lo expresa
como un `Protocol` (`src/tequio/Core/Pipeline/Pipeline.py`), así que **no heredas de nada**:
basta con tener la firma correcta (duck typing estructural).

```python
from collections.abc import Callable
from typing import Any, Protocol

class Pipe(Protocol):
    def handle(self, passable: Any, next: Callable[[Any], Any]) -> Any: ...
```

- `passable`: el objeto que viaja por el pipeline.
- `next`: la continuación. Llamar `next(passable)` ejecuta el resto de la cadena (las
  etapas siguientes y, al final, el destino). **No** llamarlo corta el flujo en seco.

> El parámetro se llama `next` a propósito, para calcar la API de Laravel (de ahí el
> `# noqa: A002` en el código).

## La API fluida

`Pipeline` encadena las etapas alrededor de un destino final. Tres pasos:

| Método | Para qué |
|--------|----------|
| `.send(passable)` | Fija el objeto que viajará por el pipeline. Devuelve `self`. |
| `.through(pipes)` | Fija las etapas, **en orden de ejecución** (una `Sequence`). Devuelve `self`. |
| `.then(destination)` | Ejecuta el pipeline y llama `destination(passable)` al final (el "núcleo de la cebolla"). |
| `.then_return()` | Ejecuta y devuelve el objeto **tal cual sale** de la última etapa (atajo de `.then(lambda x: x)`). |

```python
Pipeline().send(x).through([A(), B()]).then(destino)   # con núcleo
Pipeline().send(x).through([A(), B()]).then_return()    # sin núcleo, devuelve x mutado
```

### Pipes EXPLÍCITOS (no auto-descubiertos)

El Pipeline es una utilidad **pura**: cero dependencias del framework, **cero discovery**.
Las etapas y su orden se pasan a la mano en `.through([...])`. Esto es deliberado: a
diferencia de las tasks o los observers (que el Registry escanea), aquí **tú** decides
qué pasos corren y en qué secuencia, y eso queda a la vista en el código que invoca el
pipeline. Reordenar = cambiar el orden de la lista.

## El modelo cebolla

`.then()` arma la cadena **de afuera hacia adentro** con `reduce`: cada pipe envuelve al
siguiente, de modo que el **primero de la lista corre primero**. Cuando una etapa llama
`next(passable)`, "entra" hacia las capas internas; cuando esa llamada regresa, el control
"sale" de vuelta. Por eso una etapa puede actuar **antes** y **después** del resto:

```python
class ConLog:
    def handle(self, passable, next):
        print("antes")           # de bajada (hacia el núcleo)
        resultado = next(passable)
        print("después")         # de subida (de vuelta)
        return resultado
```

Y por eso una etapa puede **cortar** el flujo simplemente no llamando a `next`:

```python
class CortaSiVacio:
    def handle(self, passable, next):
        if not passable.body:
            return passable      # no llama next() → las etapas siguientes NO corren
        return next(passable)
```

## Ejemplo real: limpiar una nota antes de persistir

El módulo de referencia [`Demo`](06-monolito-modular.md) usa un Pipeline para **normalizar
el contenido de una nota** antes de guardarla. Lo que viaja es un `NoteDraft` (un
`dataclass` mutable con `title` y `body`), y cada etapa lo limpia un poco más.

Las etapas viven en `src/tequio/Modules/Demo/Pipes/CleanContent.py` (el archivo lleva el
nombre del **tema** —la limpieza— como en milpa). Nota que **no heredan** de `Pipe`: solo
cumplen la firma `handle(draft, next)`.

```python
# src/tequio/Modules/Demo/Pipes/CleanContent.py
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

@dataclass
class NoteDraft:
    """Lo que viaja por el pipeline: el contenido crudo de la nota, mutable etapa a etapa."""
    title: str
    body: str

class TrimContent:
    """Recorta espacios al inicio/fin del título y del cuerpo."""
    def handle(self, draft: NoteDraft, next: Callable[[Any], Any]) -> Any:
        draft.title = draft.title.strip()
        draft.body = draft.body.strip()
        return next(draft)

class CollapseWhitespace:
    """Colapsa los espacios internos del título a uno solo (evita "Hola    mundo")."""
    def handle(self, draft: NoteDraft, next: Callable[[Any], Any]) -> Any:
        draft.title = " ".join(draft.title.split())
        return next(draft)
```

El `NoteService.create` (`src/tequio/Modules/Demo/Services/NoteService.py`) los enchufa
**antes** de construir el modelo y persistir:

```python
from tequio.Core.Pipeline import Pipeline
from tequio.Modules.Demo.Pipes.CleanContent import CollapseWhitespace, NoteDraft, TrimContent

class NoteService:
    @transactional
    def create(self, title: str, body: str) -> dict[str, Any]:
        # estilo milpa: el contenido se NORMALIZA con un Pipeline (etapas componibles)
        # antes de persistir, en vez de strip()/split() sueltos.
        draft: NoteDraft = (
            Pipeline()
            .send(NoteDraft(title=title, body=body))
            .through([TrimContent(), CollapseWhitespace()])
            .then_return()
        )
        note = Note(title=draft.title, body=draft.body)
        current_session().add(note)
        current_session().flush()   # asigna PK
        return note_dict(note)
```

Aquí no hay núcleo que correr al final (no transformamos hacia un valor distinto, solo
mutamos el `draft`), así que se usa `.then_return()` para recuperar el `NoteDraft` ya
limpio.

## Forma tradicional vs. estilo milpa

**Forma tradicional** — la limpieza vive como líneas sueltas dentro del service. Funciona,
pero cada paso está amarrado a este método; reusarlos o reordenarlos significa copiar y
pegar:

```python
def create(self, title, body):
    title = title.strip()
    body = body.strip()
    title = " ".join(title.split())
    note = Note(title=title, body=body)
    ...
```

**Estilo milpa** — cada paso es un `Pipe` con nombre, componible y reordenable; el service
solo declara *qué* etapas y *en qué orden*. Agregar un paso (p. ej. `StripHtml()`) es
añadir una clase y meterla en la lista, sin tocar la lógica de los demás:

```python
.through([TrimContent(), CollapseWhitespace(), StripHtml()])
```

El Pipeline es **opt-in**: si un caso es trivial, un `title.strip()` directo está bien.
Sácalo a etapas cuando los pasos crezcan, se repitan entre servicios, o quieras poder
reordenarlos sin reescribir el método.

## Pipes con estado (parametrizados)

Como un pipe es un objeto, su `__init__` puede recibir configuración. Eso te permite
reusar la misma etapa con distintos parámetros:

```python
class MaxLength:
    def __init__(self, limit: int) -> None:
        self._limit = limit

    def handle(self, draft: NoteDraft, next):
        draft.title = draft.title[: self._limit]
        return next(draft)

# ...
.through([TrimContent(), MaxLength(120)])
```

## Notas

- El Pipeline **muta** el objeto que le pasas si las etapas escriben sobre él (como el
  `NoteDraft` del ejemplo). Si necesitas inmutabilidad, que cada etapa devuelva una copia
  y la pase a `next`.
- No es asíncrono: las etapas corren en orden, en el mismo hilo. Encaja con la regla de
  tequio de mantener el código de dominio síncrono.
- Es **independiente del framework**: puedes pasar por el pipeline cualquier objeto, no
  solo modelos ni DTOs.

## Siguiente paso

[Correo](20-correo.md).
