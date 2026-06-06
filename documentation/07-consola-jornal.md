# Consola (`tequio` / `jornal`)

tequio trae un CLI estilo `artisan`. Hay **dos formas de invocarlo**, ambas corren el
mismo kernel de consola:

- **`tequio`** — el comando que se instala en el `PATH` al hacer `pip install tequio-core`
  (entry point `tequio = tequio.Core.Console.Cli:run` en `pyproject.toml`).
- **`./jornal`** — un launcher fino en la **raíz del proyecto** (mismo nombre que en
  milpa, a propósito). Es solo `from tequio.Core.Console.Cli import run; run()`, para
  tenerlo a la mano sin instalar el paquete en el `PATH`.

```bash
tequio list                          # lista TODOS los comandos
uv run python jornal list            # idéntico, vía el launcher raíz
./jornal list                        # si el venv está activo
tequio --help                        # ayuda de Typer (solo grupos)
```

El kernel real vive en `tequio/Core/Console/Cli.py`; el `jornal` de la raíz no contiene
lógica.

## Comandos incluidos

| Comando | Qué hace | Equivalente Laravel |
|---------|----------|---------------------|
| `tequio list` | Lista todos los comandos agrupados, con su ayuda (tabla rich coloreada). | `php artisan list` |
| `tequio new <proyecto> [--demo]` | Crea un proyecto nuevo desde la plantilla embebida. | `laravel new` |
| `tequio make <generador> ...` | Genera stubs (modelo, job, handler, …). Ver abajo. | `php artisan make:*` |
| `tequio migrate make/run/status/rollback` | Migraciones de esquema con Alembic. | `php artisan migrate*` |
| `tequio db seed` | Corre los seeders descubiertos. | `php artisan db:seed` |
| `tequio db fresh` | Baja todo, re-migra y siembra. **Destructivo.** | `php artisan migrate:fresh --seed` |
| `tequio queue work` | Arranca el worker de Celery (procesa las tareas). | `php artisan queue:work` |
| `tequio schedule work` | Arranca el beat (despertador de crons). Una sola instancia. | `php artisan schedule:work` |
| `tequio schedule run` | Despacha los crons que tocan este minuto. Lo llama el crontab del SO. | `php artisan schedule:run` |

```bash
tequio queue work --queue emails,reports --concurrency 8
tequio migrate make -m "crear tabla facturas"
tequio migrate run
```

Ver [Colas y tareas](13-colas-y-tareas.md) y [Programación (cron)](14-programacion-cron.md)
para `queue work` / `schedule run` / `schedule work`, y
[Base de datos](08-base-de-datos.md) para `migrate` / `db`.

> En milpa hay además un `jornal serve` que levanta uvicorn. En tequio **no existe**:
> no hay capa HTTP que servir. Eso vive en [milpa](https://github.com/calcifux/milpa).

## `new`: crear un proyecto

`tequio new <proyecto>` copia un skeleton embebido (se localiza con
`importlib.resources`, no con aritmética de `__file__`) y deja un proyecto listo para
correr: `app/`, `jornal`, `.env` (copiado de `.env.example`) y `migrations/`, con la
config apuntando a TU código (`MODULES_PACKAGE=app.Modules…`).

```bash
tequio new mi-servicio
cd mi-servicio
uv sync                       # instala tequio + dependencias
python jornal list            # ve los comandos disponibles
```

Con `--demo` (alias `--full-demo`) copia además el **módulo Demo**: el sistema worker-side
completo de referencia (notas + eventos/observers + Mediator/Pipeline + jobs/crons +
factories/seeders), su modelo `Note` y la migración de la tabla `notes`, reescribiendo los
imports del framework (`tequio.Modules`/`tequio.Models`) a los del proyecto (`app.*`):

```bash
tequio new mi-servicio --demo
cd mi-servicio
uv sync
python jornal migrate run      # aplica la migración que ya trae el demo
python jornal db seed          # puebla notas (DemoSeeder)
python jornal queue work       # arranca el worker (procesa los @job)
```

Es seguro: si el destino existe y no está vacío, aborta con `FileExistsError` (nunca
sobrescribe trabajo del usuario).

## `make`: los 11 generadores

`tequio make <generador>` produce un stub idiomático y lo monta **por convención** (no
hay que registrarlo a mano). Es **idempotente**: nunca sobrescribe un archivo existente
(si ya existe, aborta con exit code `1`). Crea la carpeta de convención y su
`__init__.py` si faltan.

Casi todos reciben primero el **módulo** y luego el nombre; `model` es la excepción
(escribe en `app/Models`, fuera de los módulos).

| Generador | Firma | Crea en | Para qué |
|-----------|-------|---------|----------|
| `make model` | `make model <Name>` | `app/Models/<Name>.py` | Modelo SQLAlchemy (con `TimestampMixin`). |
| `make repository` | `make repository <Module> <Model>` | `Modules/<M>/Repositories/<Model>Repository.py` | `Repository[Model, int]` (CRUD tipado). |
| `make service` | `make service <Module> <Name>` | `Modules/<M>/Services/<Name>Service.py` | Caso de uso en UNA transacción (`@transactional`). |
| `make serializer` | `make serializer <Module> <Name>` | `Modules/<M>/Serializers/<Name>Serializer.py` | Función `modelo → dict` JSON-able. |
| `make factory` | `make factory <Module> <Model>` | `Modules/<M>/Factories/<Model>Factory.py` | `Factory[Model]` con datos Faker. |
| `make seeder` | `make seeder <Module> <Name>` | `Modules/<M>/Seeders/<Name>Seeder.py` | `Seeder` (se auto-descubre en `db seed`). |
| `make job` | `make job <Module> <Name>` | `Modules/<M>/Jobs/<Name>.py` | Job de background (`@job` + `.dispatch()`). |
| `make observer` | `make observer <Module> <Name>` | `Modules/<M>/Observers/<Name>Observer.py` | Observer (+ su evento) — patrón Events. |
| `make handler` | `make handler <Module> <Name>` | `Modules/<M>/Handlers/<Name>Handler.py` | Command handler — patrón Mediator. |
| `make pipe` | `make pipe <Module> <Name>` | `Modules/<M>/Pipes/<Name>.py` | Etapa de un Pipeline. |
| `make mailable` | `make mailable <Module> <Name>` | `Modules/<M>/Mail/<Name>Mailable.py` | Mailable (`build() -> MailContent`); el stub encola a la cola `emails`. |

```bash
tequio make model Invoice
tequio make repository Billing Invoice
tequio make job Billing NightlyClose
tequio make handler Billing ClosePeriod
tequio make mailable Billing InvoicePaid
# ✓ creado: app/Modules/Billing/Mail/InvoicePaidMailable.py
```

> Los generadores escriben bajo `APP_DIR` (default `app/`), que se resuelve en **cada
> llamada** relativo al `cwd` donde corres `tequio` — no a la ubicación del paquete
> instalado en `site-packages`.

## `migrate`, `db`, `queue`, `schedule`

Estos comandos son **grupos**: se invocan como `<grupo> <subcomando>`.

```bash
tequio migrate make -m "crear notas" --autogenerate   # genera una revisión (o --empty)
tequio migrate run --to head                            # aplica las pendientes
tequio migrate status                                   # revisión actual + historial
tequio migrate rollback --to -1                         # revierte una revisión

tequio db seed                                          # corre los seeders descubiertos
tequio db fresh --force                                 # baja, re-migra y siembra (destructivo)

tequio queue work --queue emails --concurrency 4 --loglevel INFO
tequio queue work --pool solo                           # fuerza el pool de ejecución de Celery
tequio schedule work --loglevel INFO                    # beat (despertador de crons)
tequio schedule run                                     # lo dispara el crontab del SO cada minuto
```

`queue work` acepta `--pool` para elegir el **pool de ejecución de Celery** (`prefork`,
`solo`, `threads`, `gevent`). Si lo omites, Celery usa su default (`prefork`) salvo en
**Windows**: ahí, si no pasas `--pool`, tequio usa `solo` automáticamente y lo avisa en el
log (el `prefork` de billiard no es confiable en Windows). Ver
[Colas y tareas](13-colas-y-tareas.md).

`queue work` y `schedule work` son procesos de **larga duración** (bloquean hasta
Ctrl-C); `schedule run` es **stateless**: despacha lo que toca este minuto y sale.
Detalles en [Colas y tareas](13-colas-y-tareas.md) y
[Programación (cron)](14-programacion-cron.md).

## Cómo funciona el descubrimiento

El launcher `jornal` solo hace `from tequio.Core.Console.Cli import run; run()`. Al
importar `Cli.py`:

1. Se importan los comandos del framework (`tequio.Core.Console.Commands`) y los del
   proyecto a nivel app (`APP_COMMANDS_PACKAGE`, default `app.Console.Commands`) con
   `import_submodules(...)`.
2. Los decoradores `@console_command` se registran en un registro interno.
3. `iter_cli_apps()` (del Registry) importa los comandos de cada módulo presente y arma
   un `typer.Typer` por **grupo**, que se monta como sub-app.

No hay lista central de comandos: se auto-descubren por convención. Por eso `Cli.py` no
declara comandos hardcodeados (salvo `list` y `new`, que son raíz).

## Crear un comando

### En un módulo

Pon el archivo bajo `Modules/<X>/Console/Commands/`. El **grupo se deduce del módulo**
(`app.Modules.Billing...` → grupo `billing`). Ejemplo real del demo
(`Modules/Demo/Console/Commands/ArchiveNoteCommand.py`):

```python
# app/Modules/Demo/Console/Commands/ArchiveNoteCommand.py
import typer

from tequio.Core.Console import console_command
from tequio.Core.Mediator import send
from tequio.Core.Registry import import_all_handlers
from tequio.Modules.Demo.Commands import ArchiveNote


@console_command(name="archive", help="Archiva una nota (vía Mediator; mismo comando que usaría un Job).")
def archive_note(note_id: int) -> None:
    # La CLI es un proceso aparte: registra a mano lo que el caso de uso necesita.
    import_all_handlers()  # handlers del Mediator (resuelve ArchiveNote -> ArchiveNoteHandler)
    result = send(ArchiveNote(note_id=note_id))
    typer.echo(f"Nota {result['id']} archivada (archived={result['archived']}).")
```

Se invoca:

```bash
tequio demo archive 7
```

### A nivel de proyecto (sin módulo)

Pon el archivo bajo `app/Console/Commands/` (`APP_COMMANDS_PACKAGE`). Aquí el grupo **no
se puede deducir**, así que es obligatorio pasarlo (si no, el decorador lanza
`ValueError` al arrancar — nunca falla en silencio):

```python
# app/Console/Commands/PingCommand.py
from tequio.Core.Console import console_command


@console_command(name="ping", group="ops", help="Verifica que el servicio responde.")
def ping() -> None:
    ...
```

```bash
tequio ops ping
```

## El decorador `console_command`

```python
def console_command(
    name: str,
    *,
    group: str | None = None,
    help: str | None = None,
    **typer_kwargs: Any,
) -> Callable[[Callable], Callable]
```

| Parámetro | Para qué |
|-----------|----------|
| `name` | Nombre del comando (ej. `"work"`, `"archive"`). |
| `group` | Grupo. Si es `None`, se deduce del path del módulo; **obligatorio** fuera de un módulo. |
| `help` | Texto de ayuda (se ve en `--help` y en `tequio list`). |
| `**typer_kwargs` | Cualquier opción extra de Typer. |

> El decorador **no envuelve** la función: queda intacta y reutilizable (puedes
> llamarla directo en tests, corre síncrona en el proceso del CLI). El comando es un
> adapter delgado y **mode-agnostic**: si quieres async, despachas un Job explícito
> (`Job.dispatch()`), no lo decides el comando.

Las opciones de cada comando son `typer.Option(...)` / `typer.Argument(...)` estándar.

## El borde de error del CLI

`run()` (en `tequio/Core/Console/Cli.py`) envuelve toda la app de Typer con un borde de
error: un `DomainError` esperado sale como **mensaje limpio + su código**, sin
traceback; un error inesperado sale conciso y su traceback completo va al log. La app de
Typer lleva `pretty_exceptions_enable=False` justo para que **nosotros** controlemos ese
render. Detalle completo en [Errores de dominio](19-errores.md).

## Siguiente paso

[Base de datos](08-base-de-datos.md).
