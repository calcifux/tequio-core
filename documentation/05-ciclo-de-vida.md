# Ciclo de vida

milpa narra el ciclo de una **petición HTTP**. tequio no tiene HTTP: su ciclo de vida es
el del **worker**. Hay tres procesos distintos (CLI, worker, beat) y un cuarto camino, el
de un `@job` despachado. Esta página los recorre, cada paso anclado al código real.

!!! info "Sin `create_app()` ni request"
    Aquí no hay una app de FastAPI ni un `_lifespan`: el equivalente al "bootstrap" es el
    arranque del CLI y la configuración de Celery. La capa HTTP vive en
    [milpa](https://github.com/calcifux/milpa).

## 1. Arranque del CLI (`jornal`)

El launcher `jornal` (en la raíz del proyecto) solo hace `from tequio.Core.Console.Cli
import run` y lo llama. El kernel de consola vive en `tequio/Core/Console/Cli.py`. Qué
pasa, en orden:

1. **`run()` configura el logging**: `setup_logging()` arma los sinks de Loguru (stderr
   conciso + archivo rotativo; `diagnose` solo en `local`). Ver [Logging](18-logging.md).
2. **Discovery de comandos** (a nivel de import del módulo `Cli`):
    - `import_submodules("tequio.Core.Console.Commands")` importa los commands del
      framework (`queue work`, `schedule work`, `schedule run`, `db`, `make`, `migrate`).
      Al importarse, sus `@console_command` se registran.
    - `import_submodules(settings.app_commands_package)` hace lo mismo con los commands
      **generales** de tu proyecto.
    - `for group, sub_app in iter_cli_apps()` recorre los módulos presentes
      (`app/Modules/*`), importa cada `Console/Commands/` (más `@console_command` que se
      registran) y arma un `typer.Typer()` por grupo, montándolo como sub-app.
3. **`app()`** despacha el subcomando que pediste. Si algo truena, el borde de error del
   CLI rinde un `DomainError` como mensaje limpio (sin traceback) y un error inesperado
   como "Error interno" + traceback completo al log.

```bash
python jornal list            # ve TODO el árbol de comandos descubiertos
```

!!! note "Discovery dinámico, no imports estáticos"
    `Cli` vive en `Core` pero **no** importa `Modules` de forma estática: el discovery es
    por rutas en string (`import_submodules` + `iter_cli_apps`). Por eso no rompe el
    contrato "Core ↛ Modules" de `import-linter`.

## 2. El worker de Celery (`queue work`)

El worker es quien **ejecuta** las tasks en background. Por sí solo no agenda nada: solo
procesa lo que se le despacha.

```bash
python jornal queue work                    # arranca el worker (bloquea hasta Ctrl-C)
python jornal queue work --queue exports    # consume solo esa(s) cola(s)
```

Qué pasa al arrancar (`tequio/Core/CeleryApp/CeleryApp.py`):

1. Se crea la `Celery(...)` con `broker=settings.effective_broker_url` y
   `backend=settings.effective_result_backend` (None por default; los crons son
   fire-and-forget). `setup_logging()` también corre aquí, para unificar el log del worker.
2. `visibility_timeout` se fija **solo** si el broker es redis/SQS
   (`broker_uses_visibility_timeout`).
3. Al terminar Celery su configuración, el hook `on_after_configure` dispara el
   **discovery diferido**:
    - `import_all_tasks()` importa `Jobs/`, `Crons/` y `Console/Commands/` de cada módulo
      presente → registra sus `@job` / `@cron_task` como tasks de Celery.
    - `import_submodules("tequio.Core.Events")` registra la task que corre los observers
      encolados.
    - `sender.conf.beat_schedule = collect_beat_schedule()` arma el calendario (lo usa el
      beat, abajo).

!!! warning "Registrar ≠ disparar"
    Que un módulo esté presente no dispara nada: registrar tasks solo las vuelve
    ejecutables bajo demanda. El único disparo automático es el beat.

## 3. El beat / scheduler (`schedule work` y `schedule run`)

El **beat** es el despertador: cada cierto tiempo despacha los crons al worker. Debe
correr **una sola** instancia.

```bash
python jornal schedule work     # arranca celery beat (bloquea hasta Ctrl-C)
```

El `beat_schedule` lo armó el discovery diferido (paso 2) con `collect_beat_schedule()`, que
**fusiona dos fuentes**: (1) los `@cron_task(schedule=…)` auto-descubiertos —su expresión cron
convertida a un `crontab` de Celery— y (2) los `beat_schedule` declarados en el
`Console/Kernel.py` de cada módulo (la vía declarativa, con **precedencia** en colisiones de
nombre). Así el beat agenda los `@cron_task` **sin** que escribas un `Kernel.py`.

Como alternativa al beat de larga duración, está `schedule run` —el `php artisan
schedule:run`— que el **crontab del SO** dispara cada minuto (lee los mismos `@cron_task`, pero
no los `Console/Kernel.py`):

```bash
* * * * *  cd /ruta/al/proyecto && python jornal schedule run
```

En cada corrida (`ScheduleRunCommand.py`):

1. `setup_logging()`; toma `SystemClock().now()` al minuto exacto (en la zona de la app).
2. Recorre `registered_crons()`. Para cada uno:
    - **Gate de entorno**: si `cron.environments` no incluye `APP_ENV`, lo salta (mismo
      gate que `@cron_task`).
    - Si `croniter.match(cron.schedule, now)` (toca este minuto), lo despacha **dentro de
      `broker_guard()`** (error claro si redis no está) a su cola o a la default.
3. Loguea cuántos despachó.

!!! note "Por qué el despertador va aparte del worker"
    `queue work` **no** embebe el scheduler (`-B`) a propósito: así una laptop de
    desarrollo nunca dispara crons sola. En prod, beat corre como su propio servicio.

## 4. El ciclo de un `@job` despachado

Este es el camino que recorre un trabajo on-demand, desde tu código hasta el worker.

```python
from app.Modules.Demo.Jobs.ExportNotesJob import export_user_notes

export_user_notes.dispatch()     # encola; NO bloquea al llamador
```

Paso a paso:

1. **`.dispatch(...)`** (`tequio/Core/Jobs/Jobs.py`) envuelve el encolado en
   **`broker_guard()`**: si el broker no responde, traduce el error crudo de kombu/redis
   en un `QueueUnavailableError` (503) con mensaje accionable, en vez de un stacktrace
   mudo. Luego hace `task.apply_async(...)` a la cola del job (aquí `exports`).
2. El **worker** (`queue work`) toma la task de la cola y la ejecuta.
3. Si el `@job` declaró `retry_for=(...)` (excepciones **transitorias**: timeouts,
   desconexiones), aplica la **`retry_policy`**: reintenta con backoff exponencial + jitter,
   con los topes de `TASK_MAX_RETRIES` / `TASK_RETRY_BACKOFF` / `TASK_RETRY_BACKOFF_MAX`
   (o lo que se pase a mano). Sin `retry_for`, es fire-and-forget.

!!! tip "job ≠ cron"
    - **`@job`** (`Core/Jobs`): lo **disparas tú** (`.dispatch()`); reintentos opt-in; sin
      lock ni env-gating. Ver [Jobs](12-jobs.md).
    - **`@cron_task`** (`Core/Cron`): lo **agenda** el scheduler; trae lock
      anti-overlapping y env-gating; nunca reintenta (se re-agenda solo). Ver
      [Programación (cron)](14-programacion-cron.md).

## Flujo completo (de un vistazo)

```
CLI:    jornal <cmd>  →  setup_logging  →  import_submodules + iter_cli_apps  →  app()
worker: queue work    →  Celery config  →  on_after_configure: import_all_tasks + beat_schedule
beat:   schedule work →  beat_schedule = @cron_task + Console/Kernel.py  →  despacha al worker
cron:   schedule run  →  croniter.match + gate environments  →  broker_guard → cola → worker
job:    .dispatch()   →  broker_guard → apply_async → worker → (retry_policy si retry_for)
```

## Siguiente paso

[Monolito modular](06-monolito-modular.md).
