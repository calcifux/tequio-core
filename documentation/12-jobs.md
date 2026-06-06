# Jobs en background (`@job`)

Un **job** es trabajo pesado que disparas **tú** desde tu código y corre en el worker, no
en el proceso que lo encola. tequio lo modela al estilo milpa (a su vez inspirado en
`Job::dispatch` de Laravel): decoras una función con `@job`, la encolas con `.dispatch(...)`
y sigues adelante sin esperar a que termine.

```python
from tequio.Modules.Demo.Jobs.ExportNotesJob import export_user_notes

export_user_notes.dispatch()   # encola y regresa ya; lo corre `jornal queue work`
```

`@job` vive en `tequio/Core/Jobs` (no en `Core/Cron`) **a propósito**: un job y un cron son
dos modelos de ejecución distintos y mezclarlos lleva a errores sutiles. Más abajo está la
tabla que los contrasta.

## Declarar un job

Decora la función con `@job` y déjala **en cualquier parte del árbol** de tu módulo (el
discovery importa todo el árbol). El módulo Demo la pone, por la convención de los
generadores `make:*`, en `tequio/Modules/Demo/Jobs/ExportNotesJob.py`:

```python
# Modules/Demo/Jobs/ExportNotesJob.py
from loguru import logger

from tequio.Core.Jobs import job
from tequio.Modules.Demo.Repositories.NoteRepository import NoteRepository


@job(name="demo.export_notes", queue="exports")
def export_user_notes() -> dict[str, int]:
    """Corre en el WORKER: reúne las notas (el 'export' real iría aquí)."""
    notes = NoteRepository().all()
    logger.info("demo.export_notes | {n} notas exportadas (en el worker)", n=len(notes))
    return {"exported": len(notes)}
```

`@job` es un wrapper fino sobre `@celery_app.task`: auto-nombra la task (`<módulo>.<func>` si
no pasas `name`), la registra y devuelve un **handle** `Job`. El descubrimiento es el mismo
que cualquier task: el Registry importa **todo el árbol** de cada módulo al arrancar y el
decorador registra la task de Celery. No hay registro nuevo que mantener.

> Para crear el archivo del job con su esqueleto ya escrito, usa el generador:
> `python jornal make job <Módulo> <NombreDelJob>` (≈ `make:job`). El stub queda en
> `Modules/<Módulo>/Jobs/<NombreDelJob>.py` por convención, listo para `.dispatch(...)` —
> de ahí lo puedes mover/aplanar si prefieres, el discovery lo encuentra igual.

### Parámetros de `@job`

| Parámetro | Tipo | Para qué |
|-----------|------|----------|
| `name` | `str \| None` | Nombre de la task. `None` = `<módulo>.<función>` (auto). |
| `queue` | `str \| None` | Cola por defecto del job (ver [Colas y tareas](13-colas-y-tareas.md)). `None` = cola por defecto. |
| `retry_for` | `tuple[type[BaseException], ...]` | Excepciones **transitorias** que disparan reintento. Vacío = fire-and-forget. |
| `max_retries` | `int \| None` | Máx. de reintentos (solo aplica con `retry_for`). `None` = `settings.task_max_retries`. |
| `bind` | `bool` | `True` da `self` como primer argumento (para leer `self.request.retries`). |

> `schedule=` está **prohibido** en `@job`: si pasas uno, lanza `ValueError`. Para tareas
> programadas usa `@cron_task` (ver [Programación (cron)](14-programacion-cron.md)).

## Disparar un job: `.dispatch()` y `.delay()`

El handle `Job` expone dos formas de encolar y una de correr síncrono:

```python
export_user_notes.dispatch()                    # encola (broker-guarded) → recomendado
export_user_notes.dispatch(queue="urgent")      # encola, sobrescribiendo la cola del decorador
export_user_notes.delay()                        # API cruda de Celery (sin broker_guard)
export_user_notes()                              # SÍNCRONO, en el proceso actual (tests)
```

- **`.dispatch(*args, queue=None, **kwargs)`** — el camino idiomático. Encola con
  `apply_async`, envuelto en `broker_guard` (ver abajo). El kwarg `queue` sobrescribe, solo
  para esa llamada, la cola declarada en `@job(queue=...)`. (El job del demo no recibe
  argumentos; uno que sí los reciba se despacha con `.dispatch(arg1, kw=…)`.)
- **`.delay(...)`** — el handle delega cualquier atributo no definido al `Task` de Celery
  (`.delay`, `.apply_async`, `.s`, `.si`, `.name`…). Úsalo para firmas/chains avanzados; ojo:
  **no** pasa por `broker_guard`, así que un broker caído sale como el stacktrace crudo de
  kombu en vez de un error limpio.
- **Llamarlo directo `export_user_notes()`** — lo corre **síncrono** en el proceso actual,
  sin encolar. Útil en tests para verificar la lógica sin levantar un worker.

### Desde dónde lo disparas

En tequio (worker-side, sin capa HTTP) disparas el job desde el código que ya corre: un
comando de consola, un observer, un service, otro job. Encolar regresa de inmediato; el
trabajo pesado corre en el worker:

```python
# Encola y sigue; el broker caído sale como QueueUnavailableError, nunca un drop mudo.
export_user_notes.dispatch()
```

No hay bloqueo: el export pesado corre en el worker mientras el llamador continúa. Para
procesar la cola, levanta el worker con `python jornal queue work` (o
`python jornal queue work --queue=exports` para consumir esa cola en particular).

!!! note "Esto en milpa"
    En milpa el disparador típico de un job es un **endpoint HTTP**, que encola y responde
    `202 Accepted` sin esperar. tequio no tiene capa web: el job se dispara desde código
    worker-side (comandos, observers, services). La capa HTTP vive en
    [milpa](https://github.com/calcifux/milpa).

## Reintentos: opt-in, solo para fallos transitorios

Por defecto un job es **fire-and-forget**: si revienta, no se reintenta. Para activar
reintentos pasa `retry_for` con las excepciones **transitorias** que sí vale la pena volver a
intentar (timeouts, desconexiones, fallos de red):

```python
@job(retry_for=(ConnectionError, TimeoutError), max_retries=5)
def sync_invoices(account_id: int) -> None:
    ...
```

Bajo el cofre, `retry_for` aplica `retry_policy(...)` de `tequio/Core/CeleryApp/Retry.py`:
cablea `autoretry_for` + backoff exponencial con jitter. Los defaults (`max_retries`, backoff
y su tope) salen de `.env` (`TASK_MAX_RETRIES`, `TASK_RETRY_BACKOFF`, `TASK_RETRY_BACKOFF_MAX`)
o los pisas a mano por job. Ver [Colas y tareas](13-colas-y-tareas.md).

> **No listes excepciones permanentes** en `retry_for` (validación, archivo inexistente):
> reintentar no las arregla y solo agota intentos. Si necesitas reintentar a mano dentro de
> la función, usa `bind=True` para recibir `self` y llamar `self.retry(...)`.

## Job vs. cron: la distinción clave

Ambos corren en el worker de Celery, pero responden a preguntas distintas. Esta es la regla
mental:

| | **Job** (`@job`, `Core/Jobs`) | **Cron** (`@cron_task`, `Core/Cron`) |
|---|---|---|
| **Quién lo dispara** | **Tú**, desde tu código (`.dispatch()`). | El **scheduler** (`jornal schedule run`, vía crontab del SO). |
| **Cuándo corre** | On-demand, cuando lo encolas. | A una cadencia fija (`schedule="*/5 * * * *"`). |
| **Reintentos** | Opt-in (`retry_for=`). | **Nunca** (se re-agenda solo en la próxima corrida). |
| **Anti-overlap (lock)** | No. | Sí (`without_overlapping`, lock en Redis). |
| **Env-gating / output routing** | No. | Sí (`environments=`, `output=`). |

La regla rápida: **si lo disparas tú** (un comando, un evento) → `@job`. **Si el reloj lo
dispara** a intervalos → `@cron_task`. Por eso un cron **no** lleva reintentos (reintentar
encima de un re-agendado duplicaría trabajo) y un job **no** lleva lock (tú controlas cuándo
y cuántas veces lo disparas).

## Broker caído → `QueueUnavailableError`

`.dispatch()` envuelve el encolado en `broker_guard()`. Si el broker (Redis por defecto) no
responde, Celery/kombu lanzarían un error de bajo nivel poco claro; `broker_guard` lo traduce
a un **`QueueUnavailableError`** con un mensaje accionable (qué falta: broker + worker, y que
existe el camino síncrono).

`QueueUnavailableError` hereda de `DomainError` (ver [Errores de dominio](19-errores.md)), así
que el borde de error del CLI lo rinde como un mensaje **limpio** con su código
`queue_unavailable`, sin escupir el traceback de kombu. Faro, no silencio: el broker caído
sale como un error claro y observable, nunca un 500 técnico ni un drop mudo.

!!! note "El status_code y RFC 9457"
    `QueueUnavailableError` carga `status_code = 503` por herencia de `DomainError`. En
    milpa, un handler HTTP global rinde ese código como `application/problem+json` (RFC 9457)
    ante un cliente web. tequio es worker-side: no hay capa HTTP, así que el `status_code`
    queda disponible en el objeto pero quien lo rinde es el borde del CLI (mensaje + código),
    no una respuesta HTTP. La capa web vive en [milpa](https://github.com/calcifux/milpa).

> `.delay()` **no** pasa por `broker_guard`: con el broker caído verías el stacktrace de
> kombu en vez del error limpio. Por eso, en código de la app, prefiere `.dispatch()`.

## Forma tradicional vs. estilo milpa

| | Forma tradicional (Celery a pelo) | Estilo milpa (`@job`) |
|---|---|---|
| Declarar | `@celery_app.task(name="...", autoretry_for=(...), max_retries=..., retry_backoff=...)` | `@job(name="...", retry_for=(...))` — el backoff sale de `.env`. |
| Encolar | `task.apply_async(args=[...], queue="...")` | `task.dispatch(..., queue="...")` |
| Broker caído | Stacktrace crudo de kombu. | `QueueUnavailableError` con mensaje accionable. |
| En tests | Levantar worker o `task.apply()`. | `task(...)` lo corre síncrono. |

El estilo milpa no te quita nada de Celery (el handle delega al `Task`), solo enmascara el
ceremonial repetitivo y el manejo del broker caído.

## Siguiente paso

[Colas y tareas](13-colas-y-tareas.md).
