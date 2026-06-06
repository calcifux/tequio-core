# Colas y tareas

tequio usa **Celery** para trabajo en background. El transporte es **agnóstico del broker**
(Redis, RabbitMQ, SQS…), se elige por `.env`, y los flujos síncronos no lo tocan.

## La app de Celery

`tequio/Core/CeleryApp/CeleryApp.py` configura la instancia `celery_app` de forma agnóstica.
Estos son los settings reales de broker (todos en `Settings`, leídos del `.env`):

| Setting (`.env`) | Default | Para qué |
|------------------|---------|----------|
| `BROKER_URL` | `""` → `redis://localhost:6379/0` | Transporte. `redis://…`, `amqp://…` (RabbitMQ), `sqs://…`. |
| `RESULT_BACKEND_URL` | `""` → sin backend | Backend de resultados. Opcional (fire-and-forget). |
| `LOCK_URL` | `""` → redis local | Store de locks para `without_overlapping` (crons). |
| `REDIS_VISIBILITY_TIMEOUT` | `3600` | Segundos antes de re-entregar una task no reconocida (redis/SQS). |

Como `BROKER_URL` y `LOCK_URL` admiten vacío, `Settings` expone las propiedades efectivas que
caen al redis local por default: `effective_broker_url`, `effective_lock_url`,
`effective_result_backend` (este último devuelve `None` cuando no hay backend). El
`visibility_timeout` solo se aplica si `broker_uses_visibility_timeout` es verdadero (redis o
SQS; RabbitMQ/AMQP lo ignora).

Otros defaults: serialización **JSON** (no pickle), `task_track_started=True`,
`result_expires=3600`, timezone de `settings.timezone`, y Loguru maneja el logging (Celery no
secuestra el root logger). Ver [Logging](18-logging.md).

> Redis local es solo un fallback de conveniencia para dev. ActiveMQ **no** es compatible con
> Celery (AMQP 1.0); usa RabbitMQ.

## Definir una task

Una task es una función decorada con `@celery_app.task`. Ponla en tu módulo (el discovery
importa todo el árbol; por la convención de los generadores `make:*`, los jobs del demo
viven en `Jobs/<Nombre>Job.py`):

```python
# Modules/Example/Jobs/HelloWorldJob.py
from loguru import logger

from tequio.Core.CeleryApp import celery_app


@celery_app.task(name="example.hello")
def hello_world(name: str = "mundo") -> str:
    logger.info("example.hello | ¡Hola, {name}! (en el worker)", name=name)
    return f"Hola, {name}!"
```

Se registra sola al importarse (el Registry importa `Jobs/` de cada módulo en
`import_all_tasks()`). No hay que listarla en ningún lado.

> En la práctica casi siempre querrás el wrapper `@job` (auto-nombre, `.dispatch()` con
> broker-guard, reintentos opt-in) en vez de `@celery_app.task` a pelo. Ver
> [Jobs (@job)](12-jobs.md).

## Despachar trabajo

```python
hello_world.delay(name="Calcifux")                          # cola por defecto
hello_world.apply_async(args=["Calcifux"], queue="reports") # cola con nombre
```

Lo procesa un worker (`jornal queue work`).

## Arrancar el worker

```bash
uv run python jornal queue work                       # cola por defecto
uv run python jornal queue work --queue reports,exports
uv run python jornal queue work --concurrency 8
```

Opciones (las del comando `queue work` real):

| Opción | Para qué |
|--------|----------|
| `--queue` | Cola(s) a consumir, separadas por coma (ej: `reports,exports`). Si se omite, consume la cola por defecto. |
| `--concurrency` | Procesos worker en paralelo. Default = nº de CPUs. |
| `--loglevel` | Nivel de log del worker. Default = `LOG_LEVEL`. |
| `--pool` | Pool de ejecución de Celery (`prefork`, `solo`, `threads`, `gevent`). Si se omite, Celery usa su default (`prefork`); en Windows tequio cae a `solo`. |

> El worker **no** arranca el scheduler. Los crons se disparan aparte (`schedule work` /
> `schedule run`), a propósito, para que una laptop de dev nunca dispare crons sola. Ver
> [Programación (cron)](14-programacion-cron.md).

### El pool de ejecución (`--pool`) y Windows

Celery puede correr las tasks con distintos **pools de concurrencia** (`prefork` por
default, `solo`, `threads`, `gevent`). El flag `--pool` te deja elegir:

```bash
uv run python jornal queue work --pool gevent     # I/O-bound: miles de conexiones en green threads
uv run python jornal queue work --pool solo       # un solo proceso, sin fork (debug / Windows)
```

> En **Windows**, si **no** pasas `--pool`, tequio usa `solo` automáticamente y lo avisa
> en el log. El `prefork` de billiard (el default de Celery) **no es confiable** en
> Windows, así que el fallback a `solo` evita cuelgues silenciosos. En Linux/macOS el
> default de Celery se respeta tal cual.

## Encolar con guarda de broker

Si el broker está caído, despachar lanza errores de bajo nivel (kombu/redis). El helper
`broker_guard()` los traduce a un `QueueUnavailableError` accionable:

```python
from tequio.Core.CeleryApp import broker_guard, QueueUnavailableError

try:
    with broker_guard():
        hello_world.delay(name="Calcifux")
except QueueUnavailableError as e:
    logger.error(e)
    # fallback: corre síncrono si tiene sentido
```

`Job.dispatch()` ya usa esto por dentro: encolar con `.dispatch(...)` es la forma idiomática
y no necesitas el `with broker_guard()` a mano. Ver [Jobs (@job)](12-jobs.md).

## Colas con nombre

Para separar cargas (ej. un worker dedicado a `exports`):

```python
task.apply_async(queue="exports")          # productor
```
```bash
uv run python jornal queue work --queue exports    # consumidor dedicado
```

Si nadie consume esa cola, el mensaje se queda ahí hasta que un worker la atienda.

## Síncrono vs. encolado

| | Síncrono | Encolado |
|--|----------|----------|
| Cómo | llamar la función directo | `.dispatch()` / `.delay()` / `.apply_async()` |
| Broker | **no** lo necesita | sí (redis/RabbitMQ/…) |
| Bloquea | sí | no |
| Cuándo | local, tests, confirmación inmediata | producción, trabajo pesado |

## Reintentos ante fallos transitorios

Una task que toca la red (HTTP, otra BD, un servicio externo) puede fallar por algo
**momentáneo**: el servicio se cayó un segundo, un timeout, la conexión se reinició. Para eso
está el helper `retry_policy(...)` (`tequio/Core/CeleryApp`): cablea `autoretry_for` +
**backoff exponencial** de forma reutilizable y **configurable de dos maneras** — por `.env` o
**a mano en código**.

```python
from tequio.Core.CeleryApp import celery_app, retry_policy

# (1) Defaults framework-wide desde .env (TASK_MAX_RETRIES / TASK_RETRY_BACKOFF / ...):
@celery_app.task(bind=True, name="sync.pull", **retry_policy(retry_for=(ConnectionError,)))
def pull_task(self, ...): ...

# (2) Configurado A MANO para ESTA task (pisa el .env, sin tocar el entorno):
@celery_app.task(
    bind=True,
    name="sync.invoices",
    **retry_policy(retry_for=(ConnectionError, TimeoutError), max_retries=5, backoff=10),
)
def sync_invoices(self, ...): ...
```

Claves de diseño:

- **Configurable a mano, no solo `.env`.** Cada parámetro de `retry_policy(...)` toma su
  default de `Settings` (`TASK_MAX_RETRIES`, `TASK_RETRY_BACKOFF`, `TASK_RETRY_BACKOFF_MAX`),
  pero se puede **fijar explícito por-task** (`max_retries=5`, `backoff=10`, `jitter=False`).
- **Solo se reintenta lo TRANSITORIO.** `retry_for` lista las excepciones que tiene sentido
  reintentar. Un fallo **permanente** (credenciales inválidas, un archivo inexistente →
  `FileNotFoundError`) **no** debe ir ahí: reintentar no lo arregla y agota intentos. Por eso
  no se usa `OSError` a secas, sino las excepciones transitorias concretas.
- **Backoff exponencial con jitter.** El reintento N espera ~`backoff · 2^(N-1)` segundos, con
  tope `backoff_max`. El `jitter` desincroniza los reintentos para no martillar al servicio
  caído justo cuando vuelve.
- **Observabilidad.** Con `bind=True` puedes loguear `intento N/total` (vía
  `self.request.retries`), así un fallo transitorio queda visible y auditable en los logs.

**Ojo con los crons** (`@cron_task`): NO les pongas `retry_policy` — un cron se reagenda solo y
ya trae lock anti-overlapping; un reintento encima duplicaría trabajo.

## Siguiente paso

[Programación (cron)](14-programacion-cron.md).
