# Monolito modular

tequio es un **monolito modular**: un solo despliegue, pero dividido en módulos
independientes sobre un kernel compartido. Es el punto medio entre el monolito
espagueti y los microservicios prematuros — sólo que aquí los módulos son
**worker-side**: jobs, crons, eventos y comandos, sin capa web.

```
            ┌───────────────────────────────────────────────┐
            │  tequio/Core  (el núcleo: Console, Jobs, Cron,  │
            │       Events, Mediator, Pipeline, Database, …)  │
            └───────────────────────────────────────────────┘
                    ▲                       ▲
                    │ usan el kernel        │
        ┌───────────┴──────┐     ┌──────────┴───────────┐
        │ app/Modules/A    │     │ app/Modules/B        │   ←  NO se importan entre sí
        └──────────────────┘     └──────────────────────┘
                    ▲                       ▲
                    └───────── comparten ───┘
              app/Models · app/Dictionaries
```

> tequio es la **extracción worker-side de milpa**: el mismo monolito modular, sin
> HTTP, Auth, Views/Vite ni i18n de UI. Esas capas viven en
> [milpa](https://github.com/calcifux/milpa). El **correo** sí viene (vuelve al worker).

## El "puerto" de un módulo

En un framework web, el puerto de un módulo es su router HTTP. En tequio **no hay
rutas**: el puerto de un módulo son sus **commands, jobs, crons, eventos y handlers**
— las maneras en que el mundo exterior (un crontab, un worker, otro proceso) lo
dispara. Un módulo tequio típico:

```
app/Modules/Billing/
  Jobs/NightlyCloseJob.py            # @job(name="billing.nightly_close")  → .dispatch()
  Crons/NightlyCloseCron.py          # @cron_task(schedule="0 3 * * *", ...)
  Console/
    Commands/
      CloseCommand.py                # @console_command(name="close")  → "tequio billing close"
  Handlers/ClosePeriodHandler.py     # @handles(ClosePeriod)  → Mediator.send(...)
  Observers/OnClosed.py              # Observer que reacciona a un evento
  Services/CloseService.py           # un caso de uso en UNA transacción (@transactional)
  Repositories/PeriodRepository.py
```

> El layout de arriba es la **convención que producen los generadores `make:*`** (carpeta
> por concern), **una propuesta de lectura**, no una imposición. tequio **liberó el
> encarpetado**: el discovery importa **todo el árbol** de cada módulo, así que organiza
> tu app como quieras —incluso aplanando todo en `Jobs.py`, `Handlers.py`, …—. La única
> convención con peso es `Console/Commands/` para el **automontaje de commands** (ver
> abajo). Lo detallamos en la sección
> [Estructura de un módulo: encarpetado libre](#estructura-de-un-modulo-encarpetado-libre).

## Las tres reglas (fronteras forzadas)

`import-linter` (guardrail de CI, `uv run lint-imports`) impone **tres contratos**
declarados en `pyproject.toml`:

### 1. El Core es worker-side: no depende de la capa web

El contrato `forbidden` más distintivo de tequio. `tequio.Core` **no puede importar**
ninguna de las librerías de la capa **web/auth** de milpa:

```toml
[[tool.importlinter.contracts]]
name = "tequio es worker-side: el Core NO depende de la capa web"
type = "forbidden"
source_modules = ["tequio.Core"]
forbidden_modules = [
    "fastapi", "starlette", "uvicorn", "slowapi",
    "httpx", "itsdangerous", "pwdlib", "jwt",
]
```

> tequio nació de extraer el lado worker de milpa: este contrato garantiza que la
> capa **web** **no se vuelva a colar** al core. Si algún día alguien hace
> `import fastapi` dentro de `tequio.Core`, el gate de CI lo rechaza.
>
> `jinja2` e `i18n` **no** están prohibidos: tequio sí manda correo (`Core/Mail`), y
> esos correos se renderizan con Jinja y se traducen con `i18nice` —todo worker-side—.
> Lo que se queda fuera es la capa **HTTP/Auth/frontend**, no el correo.

### 2. El shared kernel no depende de los módulos

`tequio.Core`, `tequio.Models` y `tequio.Dictionaries` no pueden importar
`tequio.Modules`:

```toml
[[tool.importlinter.contracts]]
name = "El shared kernel (Core/Models/Dictionaries) NO depende de los módulos"
type = "forbidden"
source_modules = ["tequio.Core", "tequio.Models", "tequio.Dictionaries"]
forbidden_modules = ["tequio.Modules"]
```

### 3. Los módulos son independientes entre sí

`app.Modules.A` no importa `app.Modules.B`. El contrato es `independence` con
wildcard, así cubre **todos** los módulos presentes sin listarlos a mano:

```toml
[[tool.importlinter.contracts]]
name = "Los módulos son independientes entre sí (no se importan unos a otros)"
type = "independence"
modules = ["tequio.Modules.*"]
```

¿Por qué estas fronteras? Para que cada módulo sea **extraíble** a un servicio propio
sin desenredar imports cruzados, y para que el kernel sea **reutilizable** tal cual en
otro proyecto.

Si dos módulos necesitan compartir algo, ese algo sube al kernel compartido
(`app/Models`, `app/Dictionaries`, o un servicio en `tequio/Core`).

## Auto-discovery: cómo el núcleo te encuentra

El kernel **no importa los módulos estáticamente** (eso violaría la frontera). En su
lugar, el `Registry` (`tequio/Core/Registry/Registry.py`) los descubre escaneando el
filesystem con `pkgutil`. Por eso agregar un módulo es solo **crear su carpeta**: no se
edita ningún archivo central.

El discovery **importa todo el árbol de cada módulo** (recursivo): por cada módulo
presente corre `import_submodules(package, recursive=True)`, que baja a los sub-paquetes
(saltando nombres que empiezan con `_`). Por eso **dónde** pongas un `@job`, un
`@cron_task`, un `Observer` o un `@handles(...)` dentro del módulo **da igual**: si está
en el árbol, se importa y su decorador/subclase se registra solo. El encarpetado es libre.

| Qué | Función del Registry | Cuándo corre | Sugerencia de lectura |
|-----|----------------------|--------------|------------|
| Comandos CLI | `iter_cli_apps()` | en `jornal` / `tequio` | `@console_command` bajo `Modules/X/Console/Commands/` |
| Jobs y crons | `import_all_tasks()` | al configurar Celery | `@job` y `@cron_task` en cualquier parte del módulo (p. ej. `Jobs/…` / `Crons/…`) |
| Crons agendados | `registered_crons()` / `collect_beat_schedule()` | en el beat (`schedule work`) y en `schedule run` (cada minuto) | `@cron_task(schedule=…)` |
| Seeders | `import_all_seeders()` | en `db seed` | subclases de `Seeder` (p. ej. `Seeders/…`) |
| Observers | `import_all_observers()` | al despachar eventos | subclases de `Observer` (p. ej. `Observers/…`) |
| Handlers (Mediator) | `import_all_handlers()` | al resolver un comando | `@handles(Cmd)` (p. ej. `Handlers/…`) |
| Modelos | `import_all_models()` | antes de migrar/sembrar | un modelo por archivo en `app/Models` |

> **Las cuatro `import_all_*` hacen lo mismo.** `import_all_tasks`, `import_all_seeders`,
> `import_all_observers` e `import_all_handlers` son hoy **alias** del mismo gesto: por
> cada módulo, `import_submodules(package, recursive=True)`. Siguen existiendo como cuatro
> nombres por **claridad del call-site** (en el código se lee *qué* se va a buscar) y por
> dejar la puerta abierta a re-especializarlas. Son idempotentes: `sys.modules` cachea, así
> que llamarlas de más no recarga nada.

`module_packages()` es la base: lista los paquetes bajo `app/Modules/` (ignora los que
empiezan con `_`). **Dónde** viven los módulos lo decide `MODULES_PACKAGE` en el `.env`
(el skeleton lo deja en `app.Modules`; en el repo del propio framework es `tequio.Modules`).

> El discovery es **dinámico** (por strings/filesystem), no por imports estáticos. Por
> eso `Core` puede descubrir módulos sin "importarlos" y sin romper la frontera
> Core ↛ Modules (que es sobre imports estáticos). El propio `Cli.py` lo dice: vive en
> Core, pero descubre los Modules con `import_submodules` + `iter_cli_apps`, no con un
> `import tequio.Modules...` hardcodeado.

## Estructura de un módulo: encarpetado libre

Aquí está el cambio de filosofía: **el encarpetado dentro de un módulo es LIBRE**. El
discovery importa **todo el árbol** del módulo, así que ya como organice el programador su
aplicación, a tequio le da igual. Puedes seguir la convención de los generadores (una
carpeta por concern), aplanar todo en archivos sueltos (`Jobs.py`, `Crons.py`,
`Observers.py`, `Handlers.py`, …), agruparlos de otra manera, o mezclar: mientras la pieza
viva en el árbol del módulo y lleve su decorador o herede de la base correcta, **se
descubre sola**. El guardrail `test_FreeLayoutDiscovery` fija esa libertad.

tequio **propone** —no obliga— una lectura, **la que producen los generadores `make:*`**:

- `Console/Commands/` — la **única convención con peso real**: es donde se hace el
  **automontaje de commands** (`@console_command`), y de su path se deduce el grupo CLI.
- `Jobs` / `Crons` / `Observers` / `Handlers` / `Services` / `Repositories` /
  `Seeders` / `Factories` / `Pipes` / `Mail` — **sugerencias de lectura** (las carpetas
  que crean los `make:*`, un archivo por clase), para que un humano ubique de un vistazo
  qué hace cada cosa. El discovery no las exige.

```
app/Modules/Billing/
  Console/Commands/CloseCommand.py   # ← convención PROPUESTA para automontar el command
  Jobs/NightlyCloseJob.py            # @job — el discovery lo importa porque está en el árbol
  Crons/NightlyCloseCron.py          # @cron_task
  Observers/OnClosed.py              # subclase(s) de Observer
  Handlers/ClosePeriodHandler.py     # @handles(...)
  Services/… · Repositories/… · Seeders/… · Factories/… · Pipes/…
```

> Lo mismo aplica si prefieres aplanar en `Jobs.py`, o si metes el job directo en
> `Services/CloseService.py`: el `import_submodules(..., recursive=True)` baja por todo el
> árbol y lo encuentra igual. **Organiza tu app como quieras.**

`MODULES_PACKAGE=app.Modules` (en el `.env`) es lo único que tequio necesita saber: el
paquete punteado donde escanear tus módulos. Cambiarlo reubica TODO el discovery sin tocar
el kernel.

## Crear un módulo

1. Crea la carpeta y siembra sus archivos con los generadores `make`
   (ver [Consola](07-consola-jornal.md)):

   ```bash
   tequio make job Billing NightlyClose      # app/Modules/Billing/Jobs/NightlyClose.py
   tequio make handler Billing ClosePeriod   # app/Modules/Billing/Handlers/ClosePeriodHandler.py
   tequio make observer Billing OnClosed      # app/Modules/Billing/Observers/OnClosedObserver.py
   tequio make service Billing Close          # app/Modules/Billing/Services/CloseService.py
   ```

   El generador crea la carpeta de **convención propuesta** y su `__init__.py` si faltan:
   agregar un módulo es **cero edición** de archivos centrales. Es solo un punto de partida
   cómodo — como el discovery importa todo el árbol, luego puedes mover esos archivos o
   aplanarlos (`Jobs.py`, `Handlers.py`, …) sin registrar nada a mano.

2. Verifica que sus comandos aparecen:

   ```bash
   tequio list
   # 🤝 Labores del tequio
   #   billing close   ...
   ```

No editas el kernel para nada. Los comandos, jobs, crons, observers, handlers y
seeders del módulo se descubren solos.

## El calendario de crons: discovery + declaración

`collect_beat_schedule()` (en el Registry) arma el `beat_schedule` —el calendario que lee el
beat— **fusionando dos fuentes** que conviven (no hay que elegir una):

- **Discovery (default, cero-config):** el discovery importa todo el árbol de cada módulo y
  registra los `@cron_task(schedule=…)` (`registered_crons()`); el Registry **convierte la
  expresión cron de cada uno a un `crontab` de Celery** y lo agenda. Defines el cron donde te
  quede y el calendario se arma solo — **sin escribir un `Kernel.py`**. (El conversor exige
  exactamente 5 campos; si no, falla con un error claro, en vez de agendar mal en silencio.)
- **Declarativo (`Console/Kernel.py`):** si prefieres ver el calendario completo en **un solo
  lugar** (estilo el `schedule()` del `Kernel` de Laravel), declaras un `beat_schedule` en
  `Modules/<X>/Console/Kernel.py`. El Registry lo integra **con precedencia**: ante una
  colisión de nombre con un `@cron_task` descubierto, gana la entrada del `Kernel.py`.

> El gate de `environments` y el lock anti-overlapping **no** se mueven: siguen viviendo en
> `@cron_task` y se aplican al **ejecutar** la task en el worker. El beat solo **agenda**.

Ver [Programación (cron)](14-programacion-cron.md).

## El kernel compartido de dominio

Dos carpetas que **sí** comparten los módulos (no son módulos, son kernel de dominio):

- `app/Models/` — modelos SQLAlchemy. Una sola fuente por tabla (todos los módulos
  comparten la BD). Ver [Modelos](09-modelos.md).
- `app/Dictionaries/` (**opcional, convención**) — constantes de dominio; import por
  submódulo. `tequio new` **no** la genera: la creas tú si la necesitas (en el propio
  paquete existe `tequio/Dictionaries/`).

> En milpa, `app/Resources/` aloja la **capa de presentación web** (vistas de páginas,
> estáticos, el frontend Vite): eso **no existe** en tequio, vive en
> [milpa](https://github.com/calcifux/milpa). Lo único que tequio sí guarda en
> `Resources/` son las **plantillas y catálogos de los correos** (las `.j2` del Mailable y
> los `.yml` del i18n de correos; ver [Correo](20-correo.md)) — son worker-side.

## Siguiente paso

[Errores de dominio](19-errores.md) — cómo el dominio expresa lo que sabe explicar sin
acoplarse al transporte.
