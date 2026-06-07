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

### Carriles focalizados: un `queue work` por cola que pesa

La forma tradicional es UN worker genérico consumiendo todas las colas. El estilo
milpa (heredado de operar `queue:work` por cola en Laravel) es **focalizar**: cada
carril pesado declara SU cola y un worker dedicado la consume — un proceso lento
jamás bloquea correos, y `supervisorctl status` te dice de un vistazo qué carril sufre.

```python
@cron_task(
    name="cfdi.generate",
    schedule=every_minutes(10),
    queue="cfdi-generate",      # cola DEDICADA: solo su worker la consume
    without_overlapping=True,
)
def generate_cfdi_task() -> dict[str, object]: ...
```

Y en el supervisor del contenedor, un `[program:]` por carril:

```ini
[program:cfdi-generate]
command=uv run python jornal queue work --queue cfdi-generate --concurrency 1

[program:worker]
command=uv run python jornal queue work --queue emails,celery --concurrency 2
```

`--concurrency 1` en el carril del cron no es tacañería: `without_overlapping` ya
garantiza UNA corrida a la vez — más hijos ahí serían RAM quemada. Se dimensiona
**por cola, a conciencia**; el día que un carril crezca, se le crece SOLO a él.

Con `QUEUE_NAMESPACE` (abajo) ambas piezas se namespacean solas: el productor
encola en `miapp.cfdi-generate` y el `--queue cfdi-generate` del consumidor se
califica igual — el carril sigue siendo carril en un broker compartido.

## Compartir un broker entre apps

Pasa en serio: dos servicios distintos apuntan **al mismo redis** (la misma `BROKER_URL`,
el mismo db) porque "ya estaba ahí". A partir de ese momento las colas son un bus
**compartido** y empiezan los robos silenciosos.

| Síntoma | Por qué pasa | Qué se ve |
|---------|--------------|-----------|
| Una corrida **se pierde** | El worker de la app B saca de la cola un mensaje de la app A cuya task **no conoce**. Celery no puede deserializarla → la **descarta** (`KeyError` / `NotRegistered`). | La task "se ejecutó" (salió de la cola) pero **nunca corrió**. Nadie se entera. |
| **Ejecución cruzada SILENCIOSA** | `mail.send`, `events.handle` y demás tasks del framework están registradas en **TODAS** las apps tequio/milpa con el **mismo nombre**. El worker de la app B sí la conoce, así que la corre… con **su** config (su SMTP, su BD). | El correo de la app A sale por el servidor de la app B. Sin error. El peor caso: parece que funciona. |

> Esto no es hipotético: le pasó al dueño en la mega-red **aqua**, con varias apps tequio/milpa
> en el mismo redis. La task desconocida = corrida perdida; `mail.send` registrada en todas =
> envíos saliendo por la app equivocada.

### El paño tibio: un db por app

Lo primero que uno intenta es darle a cada app **su propio db de redis** (`…/0`, `…/1`, `…/2`
en la `BROKER_URL`). Funciona… hasta que llegas a **Redis Cluster**, que solo expone el **db
0**. Ahí todas las apps vuelven a caer en el mismo espacio y el problema regresa. El db-por-app
es una mitigación de juguete, no una solución durable.

### La solución durable: `QUEUE_NAMESPACE`

Le das a cada app un **prefijo de colas** y deja de existir el cruce: cada worker consume
**solo lo suyo** dentro del MISMO db (por eso **sobrevive en Redis Cluster**).

```bash
# app A
QUEUE_NAMESPACE=ventas
# app B
QUEUE_NAMESPACE=reportes
```

Con un namespace activo (ej. `ventas`):

- La **cola por defecto** pasa de `celery` a `ventas.celery` (vía `task_default_queue`). Esto
  cubre TODO lo que se despacha **sin** `queue=` explícito: `events.handle`, un `Mail.queue`
  sin cola, los jobs y crons a la default. Ahí estaba el cruce silencioso de `mail.send`/
  `events.handle` — y ahí se corta.
- Las **colas con nombre** se prefijan: `emails` → `ventas.emails`, `reports` → `ventas.reports`.
  Tú sigues tecleando `emails`; el prefijo lo pone el framework en un solo lugar.
- El **lock anti-overlapping** de los crons también se namespacea: `cron-lock:<name>` →
  `cron-lock:ventas:<name>`, para que dos apps con un cron homónimo no compartan lock (ver
  [Programación (cron)](14-programacion-cron.md)).

Vacío (el **default**) = comportamiento de siempre, **100% retrocompatible**: sin prefijo, las
keys actuales intactas. No tienes que hacer nada hasta que de verdad compartas un broker.

Arrancar el worker no cambia: tú pides la cola lógica y el framework la califica.

```bash
# app A (QUEUE_NAMESPACE=ventas) — consume ventas.celery + ventas.emails
uv run python jornal queue work --queue celery,emails
```

> Bajo el capó vive un resolvedor único — `qualified_queue(name)` en
> `tequio/Core/CeleryApp/Dispatch.py` (junto a `broker_guard`) — por el que pasa **cada**
> call-site que despacha con `queue=` explícito. Un solo lugar aplica el prefijo, así no hay
> dos reglas distintas regándose por el código.

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
