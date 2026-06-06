# Eventos y Observers

Los eventos en tequio siguen el patrón **Events / Listeners** de Laravel: un hecho de
dominio ("se exportaron las notas", "se creó una nota") se dispara **explícitamente** y uno o
varios **Observers** reaccionan. Es notificación **1:N fire-and-forget**: el código que dispara
el evento no espera retorno ni sabe quién escucha.

```python
from tequio.Core.Events import dispatch
from tequio.Modules.Demo.Events import NoteCreated

dispatch(NoteCreated(note_id=7, title="Mi nota"))
```

!!! warning "NO es un model-observer de SQLAlchemy"
    tequio **no** ata esto a la base de datos. El evento **no** se dispara por un `commit`;
    lo disparas **tú** con `dispatch(...)` desde donde ocurra el hecho de negocio (un service,
    un job, un command de consola). Así controlas exactamente cuándo y con qué datos se notifica.

## El evento: un `@dataclass` de primitivos

Un evento es solo un `@dataclass` con campos **primitivos planos** (str, int, listas de
str, ids). Nada de instancias ORM ni sesiones de BD. La razón es el transporte: si hay
broker, el evento viaja como kwargs JSON y se **reconstruye en el worker** con
`Evento(**kwargs)` — y eso solo funciona con primitivos serializables (mismo contrato que
`SerializesModels` de Laravel).

```python
# src/tequio/Modules/Demo/Events.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class NoteCreated:
    """Se creó una nota. Lo observa LogNoteCreated."""
    note_id: int
    title: str
```

!!! tip "Empaca en el evento lo que el observer necesitará lejos del caller"
    Un observer puede correr en el **worker**, en otro proceso: allá no tiene la sesión ni el
    contexto del caller. Por eso el evento lleva **dentro** los datos que el observer usará
    (`note_id`, `title`) en vez de un objeto ORM. Si necesitas datos de BD que sí puedes leer
    por id, pasa el id y consúltalo en `handle()`.

!!! note "En milpa esto mandaba correo al dueño"
    En milpa, `NoteCreated` cargaba el **dueño** y su `locale`, y el observer enviaba un
    `Mailable` i18n a ese usuario. tequio **sí tiene correo** (vuelve al worker; ver
    [Correo](20-correo.md)), pero **no tiene Auth ni tabla de usuarios** (eso vive en
    [milpa](https://github.com/calcifux/milpa)), así que el demo ya **no tiene dueño**: el
    evento se quedó mínimo (`note_id`, `title`). El observer del demo (`LogNoteCreated`) solo
    **loguea** —a propósito— para mostrar el **otro transporte** de un efecto secundario; el
    correo del demo lo manda el cron del digest (ver [Programación (cron)](14-programacion-cron.md)).

## El Observer: subclase con `observes` + `handle()`

Un Observer hereda de la ABC `Observer` (`tequio/Core/Events/Observer.py`), fija el atributo
de clase `observes = TipoDeEvento` y sobreescribe `handle(self, event)`:

```python
# src/tequio/Modules/Demo/Observers/LogNoteCreated.py
from __future__ import annotations
from loguru import logger

from tequio.Core.Events import Observer
from tequio.Modules.Demo.Events import NoteCreated

class LogNoteCreated(Observer):
    observes = NoteCreated

    def handle(self, event: object) -> None:
        assert isinstance(event, NoteCreated)  # dispatch ya filtró por tipo; narrow para mypy
        # en milpa esto era un Mailable i18n al dueño; aquí, sin dueño, el observer loguea
        # (el correo del demo lo manda el cron del digest: muestra el otro transporte)
        logger.info(
            'demo.note_created | nota {id} "{t}" creada',
            id=event.note_id, t=event.title,
        )
```

| Atributo / método | Para qué | Laravel |
|-------------------|----------|---------|
| `observes` (ClassVar) | Tipo de evento que escucha. Match por tipo **exacto** (sin herencia). `None` = escucha **todos** los eventos. | `$listen` en `EventServiceProvider` |
| `handle(self, event)` | Reacciona al evento. Por defecto no hace nada. | `handle(Event $event)` |

Relación **1:N**: varios Observers pueden declarar `observes = NoteCreated` y todos
corren. El `event` que llega a `handle()` ya está filtrado por tipo (de ahí el `assert
isinstance` para que mypy lo afine).

!!! note "Un Observer SÍ puede leer la BD"
    Lo que evitamos es **atarlo** a la BD (no es un model-observer). Pero `handle()` es código
    normal: puede consultar repositorios, escribir a un archivo, despachar otro job, etc. El
    observer del demo no toca BD porque todo lo que necesita viaja en el evento.

## Disparar el evento: `dispatch(evento)`

`dispatch` vive en `tequio/Core/Events`. Recibe la **instancia** del evento y la entrega a cada
Observer cuyo `observes` matchee (o sea `None`):

```python
from tequio.Core.Events import dispatch
from tequio.Modules.Demo.Events import NoteCreated

dispatch(
    NoteCreated(
        note_id=7,
        title="Mi nota",
    )
)
```

En tequio el disparo nace **donde ocurre el hecho de negocio**: un service que acaba de crear
la nota, un [job](12-jobs.md) o un command de consola. Por ejemplo, justo después de crear la
nota en un service:

```python
created = NoteService().create(title, body)
# Evento de dominio → el Observer LogNoteCreated loguea la creación (auto).
dispatch(
    NoteCreated(
        note_id=int(created["id"]),
        title=str(created["title"]),
    )
)
```

!!! info "El demo trae el evento y el observer, no el call site"
    El módulo `Demo` define `NoteCreated` y `LogNoteCreated` para enseñar el patrón,
    pero **no incluye** un caller que lo dispare (en milpa ese call site era el controller HTTP
    `POST /notes`, que tequio no tiene). Tú decides desde dónde llamas `dispatch(...)`: cualquier
    service, job o command es válido.

## Transporte adaptativo: broker si hay, síncrono si no

Aquí está la decisión clave de diseño (KISS, sin flags por-observer): **si hay broker
disponible, el observer corre en el worker (async); si no, corre síncrono inline.** Tú no
eliges; lo decide el framework por observer:

```
dispatch(NoteCreated(...))
        │
        ▼
  ¿hay broker?
   ├── sí → encola task "events.handle" → el WORKER reconstruye observer + evento y corre handle()
   └── no → observer().handle(event)   (síncrono, en el acto)
```

El import de Celery es **perezoso**: un proyecto que nunca encola observers no jala redis al
arrancar. La rama encolada vive en `tequio/Core/Events/Tasks.py` y solo se importa cuando hace
falta (lo hace `Dispatch._dispatch_one`). Si el broker no responde, se cae a ejecución
síncrona automáticamente (`QueueUnavailableError`).

!!! info "Best-effort por observer"
    Un observer que falla **no tumba al caller** ni a los demás observers: un efecto
    secundario no debe romper la operación de negocio. El comportamiento ante un error lo
    decide el flag `EVENTS_STRICT` (siguiente sección) — pero **nunca** falla en silencio.

## Auto-registro y discovery

No hay que registrar nada a mano (adiós al `EventServiceProvider`). Dos mecanismos:

1. **Auto-registro por subclase**: definir una clase que herede de `Observer` la mete sola
   en el registro interno (`__init_subclass__`), mismo patrón que los `Seeder`.
2. **Discovery por convención**: `import_all_observers()` (en `tequio.Core.Registry`) importa
   **todo el árbol** de cada módulo (recursivo). Importar el módulo donde vive el observer es
   lo que dispara su auto-registro.

Por eso basta con que el `Observer` viva **en algún lugar del árbol de tu módulo** (el demo lo
pone en `Observers/LogNoteCreated.py`, pero el discovery no lo exige ahí). Si lo defines fuera del paquete de
módulos y nadie lo importa, `dispatch` no lo verá.

!!! tip "Procesos sueltos: corre el discovery a mano"
    Un proceso que dispare eventos fuera del arranque normal (un command de consola propio, un
    script) debe importar los observers antes para que `dispatch` los encuentre:

    ```python
    from tequio.Core.Registry import import_all_observers
    import_all_observers()  # registra las subclases de Observer; sin esto, cero listeners
    ```

## El flag `EVENTS_STRICT`

Controla qué pasa cuando un observer **lanza una excepción** (setting `events_strict`, definido
en `tequio/Core/Config`, default `False`):

| `events_strict` | Comportamiento ante un observer que falla | Cuándo |
|-----------------|-------------------------------------------|--------|
| `False` (default) | Loguea **ruidoso** (ERROR + traceback con `logger.exception`) y sigue. La operación de negocio no se rompe. | Producción |
| `True` | **Re-lanza** la excepción, para que el bug del observer truene fuerte de inmediato. | Dev / tests |

En ambos casos **nunca** se traga el error en silencio. Pon `EVENTS_STRICT=true` en `.env`
mientras desarrollas para cazar bugs en tus observers al instante.

## Forma tradicional vs. estilo milpa

**Forma tradicional** — el service orquesta los efectos secundarios inline. Sabe del log y
del transporte; mezcla la regla de negocio con sus consecuencias:

```python
def create(self, title, body):
    note = ...  # crear y persistir la nota
    # El service orquesta TODO el efecto secundario a mano:
    logger.info("nota {id} creada", id=note.id)
    # y si mañana hay que auditar o avisar a otro sistema → se toca este método otra vez
    return note
```

Agregar un segundo efecto (auditoría, webhook, export) significa tocar el service otra vez.

**Estilo milpa** — el service **anuncia el hecho** y se desentiende del resto. Quién
reacciona y cómo viaja (worker o síncrono) es problema del framework y de los Observers:

```python
def create(self, title, body):
    note = ...  # crear y persistir la nota
    dispatch(NoteCreated(note_id=note.id, title=note.title))
    return note
```

Para sumar un efecto, **agregas un Observer** (otra subclase de `Observer` con
`observes = NoteCreated`) — sin tocar el service. Eso es la inversión 1:N: el emisor
no conoce a sus consumidores.

## Eventos vs. Mediator vs. Jobs

tequio ofrece varios mecanismos opt-in; elige por intención:

| Patrón | Cardinalidad | ¿Devuelve? | Cuándo |
|--------|--------------|------------|--------|
| **Eventos / Observers** (`dispatch`) | 1:N | No (fire-and-forget) | "Pasó X" — notificar a N reacciones desacopladas. |
| **Mediator** (`send`) | 1:1 | Sí (resultado) | Una intención que **resuelves** y de la que esperas respuesta. |
| **Jobs** (`@job` + `.dispatch()`) | 1:1 | No | Un trabajo de background concreto que **siempre** quieres encolar. |

El Mediator enruta UNA intención a UN handler y te devuelve el resultado; los Eventos son
notificación 1:N donde no esperas retorno y el transporte lo decide el framework. Ver
[Jobs](12-jobs.md) y [Colas y tareas](13-colas-y-tareas.md) para el background.

## Probar Observers sin BD ni broker

Como los observers se ejecutan síncronos cuando no hay broker, un test puede disparar el
evento y verificar el efecto sin Celery. Para aislar el registro entre tests, tequio expone
helpers (espejo de los seeders):

```python
from tequio.Core.Events import dispatch, registered_observers, reset_observers
```

- `registered_observers()`: la lista de subclases de `Observer` registradas.
- `reset_observers()`: limpia el registro (**solo** para tests).

Con `EVENTS_STRICT=true` en el entorno de test, si un observer falla, el `dispatch` re-lanza
y el test truena (en vez de tragarse el error).

## Siguiente paso

[Mediator (command bus)](16-mediator.md).
