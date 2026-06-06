# Programación (cron)

tequio reproduce el **scheduler estilo milpa** (a su vez inspirado en el de Laravel) sobre
Celery: declaras la cadencia pegada al job con `@cron_task`, y un disparador despacha lo que
toca. Hay dos disparadores que leen esos mismos crons: el **beat** de Celery
(`schedule work`, que los **auto-agenda**) o el **crontab del SO** llamando `schedule run`
cada minuto (estilo `php artisan schedule:run`).

## Declarar un cron

Declara tus crons con `@cron_task` dentro de tu módulo (el discovery importa todo el árbol;
el demo los pone, por la convención de los generadores `make:*`, en
`Crons/DailyDigestCron.py`). El módulo Demo trae uno en
`tequio/Modules/Demo/Crons/DailyDigestCron.py` — un **resumen diario de notas**:

```python
# Modules/Demo/Crons/DailyDigestCron.py
from tequio.Core.CeleryApp import QueueUnavailableError
from tequio.Core.Cron import cron_task, daily_at
from tequio.Core.Mail import Mail
from tequio.Modules.Demo.Mail.DailyDigestMailable import DailyDigestMailable
from tequio.Modules.Demo.Repositories.NoteRepository import NoteRepository


@cron_task(name="demo.daily_digest", schedule=daily_at("08:00"), output="demo_digest")
def daily_digest() -> None:
    """Corre en el WORKER cada día a las 8:00 (lo despacha el beat de `schedule work`,
    o el crontab del SO vía `schedule run`)."""
    total = len(NoteRepository().all())
    # El cron MANDA correo. Worker-side lo idiomático es ENCOLAR a la cola `emails`
    # (= ->onQueue('emails') de Laravel; la consume `queue work --queue emails`); si el
    # broker no está, caemos al envío SÍNCRONO. Con MAIL_DRIVER=log (default dev) el MIME
    # se vuelca al log —a logs/cron_demo_digest.log por su `output`— sin SMTP; con Mailpit, a la UI.
    mailable = DailyDigestMailable(total=total)
    try:
        Mail.queue(mailable, to=["admin@example.com"], queue="emails")
    except QueueUnavailableError:
        Mail.send(mailable, to=["admin@example.com"])
```

Se registra al importarse (el Registry importa **todo el árbol** de cada módulo).

!!! note "El cron que motivó traer el correo al worker"
    Este es justo el caso por el que tequio **sí extrajo el correo** de milpa: en milpa el
    `DailyDigestCron` **manda el resumen por correo** al admin, y muchísimos crons reales
    terminan haciendo lo mismo. Así que aquí el digest **manda correo de verdad** (un
    `Mailable` encolado a la cola `emails`, con fallback síncrono si el broker no está);
    con el driver `log` (default dev) se vuelca al log sin SMTP, con
    Mailpit lo ves en la UI. Lo que tequio **no** trae es la capa **web** que lo disparaba;
    el patrón del cron (cadencia + guards + despacho al worker) es idéntico al de milpa. Ver
    [Correo](20-correo.md).

## El decorador `@cron_task`

```python
def cron_task(
    *,
    name: str,
    schedule: str | None = None,
    queue: str | None = None,
    environments: Sequence[str] | None = None,
    without_overlapping: bool = False,
    output: str | None = None,
    lock_timeout: int | None = None,
    **celery_options: Any,
) -> Callable[[DecoratedTask], Any]
```

| Parámetro | Default | Semántica |
|-----------|---------|-----------|
| `name` | (obligatorio) | Identificador único de la task. |
| `schedule` | `None` | Expresión cron (5 campos). Si es `None`, la task existe pero no se agenda. |
| `queue` | `None` | Cola de Celery a la que se despacha; `None` = cola por defecto. |
| `environments` | `None` → todos | Lista de `APP_ENV` donde corre; si `app_env` no está, se omite. |
| `without_overlapping` | `False` | Lock en Redis; si la corrida previa sigue, se omite esta. |
| `output` | `None` | Rutea los logs de la corrida a `logs/cron_<output>.log` (rotación diaria, 14 días). |
| `lock_timeout` | derivado | Timeout del lock. Por defecto `visibility_timeout + 300s`. |
| `**celery_options` | — | Cualquier opción extra de Celery (`rate_limit`, etc.). |

> `@cron_task` **sí envuelve** la función: la wrapper ejecuta los guards (entorno, lock, logs)
> antes de tu código, y devuelve una task de Celery. Puedes llamarla con `.delay()` o directo
> `task()`.

```python
@cron_task(
    name="reminders",
    schedule=every_five_minutes(),
    environments=["qa", "production"],
    without_overlapping=True,
    output="reminders",
    queue="reports",
)
def send_reminders() -> None:
    logger.info("Procesando recordatorios...")
    # ...
```

> No hay generador `make cron`: los crons se escriben a mano bajo `Modules/<X>/Crons/`. (El
> generador `make job` sí existe, para jobs on-demand; ver [Jobs (@job)](12-jobs.md).)

## Cadencia: helpers de `Schedule`

En vez de escribir cron raw, usa los helpers (`tequio/Core/Cron`). Cada uno devuelve una
expresión cron (string de 5 campos) que pasas a `@cron_task(schedule=...)`:

| Helper | Cron |
|--------|------|
| `every_minute()` | `* * * * *` |
| `every_minutes(n)` | `*/n * * * *` (n entre 1 y 59) |
| `every_five_minutes()` | `*/5 * * * *` |
| `every_ten_minutes()` | `*/10 * * * *` |
| `every_fifteen_minutes()` | `*/15 * * * *` |
| `every_thirty_minutes()` | `*/30 * * * *` |
| `hourly()` | `0 * * * *` |
| `hourly_at(min)` | `<min> * * * *` |
| `daily()` | `0 0 * * *` |
| `daily_at("HH:MM")` | `<m> <h> * * *` |
| `weekly()` | `0 0 * * 0` |
| `monthly()` | `0 0 1 * *` |
| `cron("expr")` | escape hatch (raw) |

```python
from tequio.Core.Cron import cron_task, daily_at, cron

@cron_task(name="backup", schedule=daily_at("02:30"), environments=["production"])
def backup() -> None: ...

@cron_task(name="reporte", schedule=cron("15 9 * * 1-5"))   # 9:15 lun-vie
def reporte() -> None: ...
```

## Cómo se disparan: `schedule work` vs `schedule run`

Hay dos modos, y **ambos** disparan los `@cron_task` que descubre el framework. **Elige uno**
(no corras los dos a la vez, o cada cron se despacharía doble):

### A) `schedule work` (beat de Celery)

`jornal schedule work` arranca el **beat** (un proceso de larga duración que despierta y
despacha los crons a la cola). **Corre una sola instancia** (varios beats = crons duplicados):

```bash
uv run python jornal schedule work
```

El beat lee su `beat_schedule`, que arma el `Registry` al configurarse Celery
(`collect_beat_schedule()`). Ese calendario es la **fusión** de dos fuentes:

1. **Los `@cron_task(schedule=…)` auto-descubiertos** — el discovery importa todo el árbol
   de cada módulo, registra los crons (`registered_crons()`), y el Registry convierte la
   expresión cron de cada uno a un `celery.schedules.crontab` y lo agenda. **Sin escribir un
   solo `Kernel.py`**: defines el cron donde te quede y el beat lo agenda solo.
2. **Los `beat_schedule` declarados en `Console/Kernel.py`** de cada módulo — la vía
   **declarativa** (estilo el `Kernel` de Laravel), para quien prefiere ver el calendario
   centralizado en un archivo. **Tiene precedencia**: si un `Kernel.py` declara una entrada
   con el mismo nombre que un `@cron_task` descubierto, gana la del `Kernel.py`.

> Arrancar el beat **sí dispara crons** según el `environments` de cada uno: el beat solo
> **agenda y despacha**; el gate de `environments` y el lock anti-overlapping siguen viviendo
> en `@cron_task` y se aplican al **ejecutar** la task en el worker. En dev normalmente no
> corres el beat: pruebas un cron a mano (`mi_cron.delay()` o `mi_cron()` directo).

!!! warning "El conversor exige 5 campos (no agenda mal en silencio)"
    Al agendar un `@cron_task`, el Registry convierte su `schedule` a un `crontab` de Celery
    mapeando los 5 campos posicionalmente (`minute hour día-del-mes mes día-de-semana`). Los
    helpers de `Schedule.py` siempre devuelven 5 campos; el escape hatch `cron("…")` pasa el
    string crudo. Si esa expresión **no tiene exactamente 5 campos**, el conversor **falla con
    un error claro** en vez de agendar algo mal (faro: un cron mal agendado que nunca dispara
    sería un fallo invisible).

### B) `schedule run` desde el crontab del SO

`jornal schedule run` es el `php artisan schedule:run`: evalúa qué crons tocan **este minuto**
(con croniter) y los despacha; arranca, despacha en milisegundos y sale (stateless). En vez de
un beat de larga duración, lo llama **el crontab del SO** cada minuto:

```cron
* * * * * cd /ruta/al/proyecto && /usr/bin/uv run python jornal schedule run
```

En cada corrida, `schedule run` recorre los crons registrados (`registered_crons()`), aplica el
mismo gate de `environments` que el decorador, y para los que `croniter.match(...)` confirma que
tocan, los despacha a la cola (a su `queue` con `apply_async`, o a la cola por defecto con
`.delay()`), todo envuelto en `broker_guard` (error claro si redis no está).

> Este modo lee los **mismos** `@cron_task` que el beat (vía `registered_crons()`), pero **no**
> mira los `Console/Kernel.py`: el `Kernel.py` declarativo solo lo honra el beat. Si declaras
> crons en `Kernel.py` y disparas con `schedule run`, esos no se despachan; usa el beat.

En ambos modos, el worker (`jornal queue work`) es quien **ejecuta** la task despachada. Ver
[Colas y tareas](13-colas-y-tareas.md).

## Los guards (en orden)

Cuando un cron se ejecuta, la wrapper aplica:

1. **Entorno** — si `environments` no está vacío y `APP_ENV` no está en la lista, se omite
   (loguea y retorna sin ejecutar).
2. **Logs** — si hay `output`, los logs de la corrida van a `logs/cron_<output>.log`.
3. **Lock** — si `without_overlapping`, toma un lock Redis `cron-lock:<name>`; si ya está
   tomado (la corrida anterior sigue), se omite.

### El invariante del lock

`lock_timeout` debe ser **mayor** que `redis_visibility_timeout`. Si fueran iguales,
expirarían juntos: Redis re-entregaría la task y un segundo worker tomaría el lock recién
liberado → **doble ejecución**. Por eso el default es `visibility_timeout + 300s`, y si pasas
un `lock_timeout` menor o igual, **falla al decorar** (no en runtime).

> El lock vive en el store de `LOCK_URL` (redis), independiente del broker: el broker puede ser
> RabbitMQ/SQS (que no tienen primitiva de lock), pero el lock siempre sale de un redis.

## Flujo completo

```
1. @cron_task registra el cron (cadencia + guards) en registered_crons().
2a. beat (schedule work): el Registry fusiona los @cron_task + los Console/Kernel.py
    en el beat_schedule; el beat despacha a la cola cuando toca el crontab celery.
2b. crontab del SO (schedule run): cada minuto → ¿toca (croniter)? ¿aplica el entorno?
    → despacha a la cola.
3. worker (queue work): ejecuta la wrapper (guards: entorno, lock, logs) → tu función.
```

> Dos disparadores, una misma fuente: ambos parten de los `@cron_task` descubiertos. El beat
> agrega la vía declarativa (`Console/Kernel.py`, con precedencia); `schedule run` no la mira.

## El reloj (`Clock`)

Para los cálculos de fechas de **negocio**, tequio trae un **reloj inyectable**
(`tequio/Core/Clock/Clock.py`), el equivalente de `java.time.Clock` de Spring o de
`Carbon::setTestNow()` de Laravel. La idea: no llamar `datetime.now()` suelto en el dominio
(eso acopla al reloj de pared y **no se puede congelar en un test**), sino recibir un `Clock` y
pedirle la hora.

Es un `Protocol` con dos implementaciones:

| Implementación | Qué hace |
|----------------|----------|
| `SystemClock` | Hora **real** en la zona de la app (`TIMEZONE` del `.env`), naive local (como guarda Eloquent/Carbon). |
| `FixedClock(moment)` | Reloj **congelado**: siempre devuelve `moment`. Para tests (= `Carbon::setTestNow`). |

```python
from tequio.Core.Clock import Clock, SystemClock, FixedClock
```

> **Cómo se inyecta:** a mano, instanciándolo donde se necesite (tequio no tiene un Unit of
> Work que lo cablee por ti). El único consumidor del core es `schedule run`, que hace
> `SystemClock().now()` para saber qué minuto es. En tu dominio, recibe un `Clock` por
> parámetro/constructor y pásale un `SystemClock()` en producción.
>
> Para los **timestamps de BD** no uses esto: los pone la BD con `func.now()` y la conexión ya
> corre en la zona de la app (ver `Database/Session.py` y `Timestamp.py`).

### Congelar el tiempo en un test de cron

Como tu cron recibe el reloj (en vez de llamar `datetime.now()` adentro), un test lo congela
pasándole un `FixedClock` y verifica el comportamiento de un instante exacto, sin esperar ni
depender de la hora real:

```python
from datetime import datetime
from tequio.Core.Clock import Clock, FixedClock


def expira_membresias(clock: Clock) -> int:
    """Marca como vencidas las membresías cuya fecha de corte ya pasó."""
    hoy = clock.now()
    # ... usa `hoy` para filtrar/decidir ...
    return 0


def test_no_expira_nada_si_el_corte_es_manana() -> None:
    # Congela el "ahora" en un instante exacto (= Carbon::setTestNow).
    clock = FixedClock(datetime(2026, 6, 6, 8, 0, 0))
    assert expira_membresias(clock) == 0
```

Y si lo que quieres es probar que un cron **toca** este minuto, `croniter.match(schedule, now)`
con un `now` que sacas del `FixedClock` te deja afirmar el agendado sin reloj de pared.

## Siguiente paso

[Eventos y Observers](15-eventos-y-observers.md).
