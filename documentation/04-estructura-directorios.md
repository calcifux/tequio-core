# Estructura de directorios

Hay dos layouts que conviene distinguir: el del **proyecto que generas** con `tequio new`
(donde escribes tu código) y el del **paquete tequio** (el framework reutilizable).

## El proyecto generado (`tequio new`)

```
mi-servicio/
  app/
    Models/          # tus modelos SQLAlchemy (un archivo por modelo; auto-discovery)
    Modules/         # tus features
      Hello/         #   módulo de ejemplo (con --demo: además Demo/)
        Console/
          Commands/  #     @console_command (se auto-montan en jornal)
    Console/
      Commands/      # comandos GENERALES del proyecto (no atados a un módulo)
  migrations/        # migraciones Alembic
    versions/        #   las revisiones (las genera `migrate make`)
    env.py           #   bootstrap de Alembic (lee DATABASE_URL + app/Models)
  logs/              # salida de Loguru (app.log, app.jsonl, cron_*.log)
  jornal             # tu consola (el "artisan") en la raíz
  .env               # tu configuración (NO se sube a git)
  .env.example       # plantilla de configuración
  docker-compose.yml # SOLO infra de dev: redis + mailpit
  pyproject.toml     # depende de tequio-core; deps de dev (pytest, faker)
```

!!! note "Sin `Resources/Views`"
    tequio es worker-side: **no hay vistas, estáticos ni traducciones**. Esa capa vive en
    [milpa](https://github.com/calcifux/milpa).

### Tu código vive fuera del paquete

El `.env` del proyecto apunta tequio a `app/` con `MODULES_PACKAGE=app.Modules`,
`MODELS_PACKAGE=app.Models`, etc. (ver [Configuración](03-configuracion.md)). Así el
framework descubre TU código sin que tengas que tocar el paquete instalado.

- `app/Models/` — modelos SQLAlchemy. Auto-descubiertos con `pkgutil` (SQLAlchemy necesita
  verlos todos para resolver relaciones por string). Un modelo por archivo.
- `app/Modules/<Nombre>/` — tus features (ver abajo).
- `app/Console/Commands/` — comandos generales del proyecto. A diferencia de los de módulo,
  estos **deben** declarar `group=` explícito en `@console_command`.

### Anatomía de un módulo

Cada módulo es autocontenido e independiente de los demás. El **encarpetado es libre**:
el discovery importa **todo el árbol** del módulo, así que sueltas la pieza donde te quede
y tequio la descubre. Ninguna carpeta es obligatoria. El módulo `Demo` (que copia
`tequio new --demo`) usa la **convención que producen los generadores `make:*`** —una
carpeta por concern, un archivo por clase— como una de las formas de organizarse:

```
app/Modules/Demo/
  __init__.py
  Commands.py                        # ArchiveNote (comando del Mediator: solo datos)
  Events.py                          # NoteCreated (evento de dominio)
  Jobs/ExportNotesJob.py             # ExportNotesJob (@job — background on-demand)
  Crons/DailyDigestCron.py           # DailyDigestCron (@cron_task — agendado)
  Observers/LogNoteCreated.py        # LogNoteCreated (Observer — reacciona a NoteCreated)
  Handlers/ArchiveNoteHandler.py     # ArchiveNoteHandler (@handles(ArchiveNote))
  Pipes/CleanContent.py              # TrimContent/CollapseWhitespace (etapas de un Pipeline)
  Services/NoteService.py            # NoteService (caso de uso en una transacción)
  Repositories/NoteRepository.py     # NoteRepository (Repository[Note, int])
  Seeders/DemoSeeder.py              # DemoSeeder (puebla la BD; lo corre `db seed`)
  Factories/factories.py             # NoteFactory (datos con Faker)
  Mail/DailyDigestMailable.py        # DailyDigestMailable (correo de resumen)
  Console/
    Commands/
      ArchiveNoteCommand.py          # @console_command → `demo archive <note_id>`
```

!!! note "Este layout es una PROPUESTA, no una imposición"
    El demo sigue la **convención que generan los `make:*`** (carpeta por concern,
    `Jobs/ExportNotesJob.py`, `Mail/DailyDigestMailable.py`, …) para que se lea de un
    vistazo. Pero el discovery no la exige: importa **todo el árbol** del módulo. Si
    prefieres aplanar (`Jobs.py`) o agrupar de otra manera, funciona igual —la pieza se
    descubre mientras lleve su decorador o herede de su base. La **única** convención con
    peso es `Console/Commands/`, donde se automontan los `@console_command`. El guardrail
    `test_FreeLayoutDiscovery` fija esta libertad.

Ver [Monolito modular](06-monolito-modular.md) para el detalle de cómo se descubre y monta
cada cosa.

## El paquete tequio (el framework)

Dentro de `src/tequio/` vive el kernel reutilizable. Es **el framework**: genérico, sin
sabor de dominio.

```
src/tequio/
  Core/              # EL FRAMEWORK (genérico, reutilizable)
    Config/          #   Settings (pydantic-settings, lee .env)
    Console/         #   kernel de consola (Typer) + @console_command + Scaffold
    CeleryApp/       #   app de Celery + dispatch (broker_guard) + retry_policy
    Cron/            #   @cron_task + helpers de cadencia (scheduler estilo Laravel)
    Jobs/            #   @job (background on-demand)
    Events/          #   eventos + Observer + dispatch
    Mediator/        #   command bus (@handles + Mediator.send)
    Pipeline/        #   Pipeline (etapas encadenadas)
    Database/        #   Base, Session, Repository, @transactional, mixins, Migrations, Seeder, Factory
    Mail/            #   Mailable + MailContent + Mailer (drivers smtp/log/null/array) + facade Mail
    View/            #   TemplateEngine (Jinja) para renderizar las plantillas de correo
    Translate/       #   t(), current_locale, set_request_locale (i18n de correos, i18nice)
    Registry/        #   auto-discovery de tasks, crons, modelos, seeders, CLI
    Errors/          #   DomainError + subclases (errores de dominio neutrales)
    Logging/         #   setup_logging (Loguru)
    Clock/           #   SystemClock (reloj inyectable)
  Models/            # modelos del propio paquete (Note; demo)
  Dictionaries/      # constantes de dominio
  Modules/Demo/      # módulo Demo (se MATERIALIZA en el proyecto con --demo)
  _skeleton/         # plantillas (.tmpl) que copia `tequio new`
  migrations/        # migraciones del propio repo (incluye la del demo)
```

### Los subsistemas del kernel

Cada subcarpeta de `Core` es un subsistema (espejo worker-side de los "componentes" de
Laravel):

| Carpeta | Equivalente Laravel | Doc |
|---------|---------------------|-----|
| `Config` | `config()` + `.env` | [Configuración](03-configuracion.md) |
| `Console` | Kernel de consola / artisan | [Consola jornal](07-consola-jornal.md) |
| `Database` | Eloquent + migraciones | [Base de datos](08-base-de-datos.md) |
| `Mail` / `View` / `Translate` | Mail (Mailables) + Blade/views + Localization | [Correo](20-correo.md) |
| `Cron` | Task Scheduling | [Programación (cron)](14-programacion-cron.md) |
| `Jobs` / `CeleryApp` | Queues / Jobs | [Jobs](12-jobs.md) · [Colas y tareas](13-colas-y-tareas.md) |
| `Events` | Events / Listeners | [Eventos y Observers](15-eventos-y-observers.md) |
| `Mediator` | — (command bus) | [Mediator](16-mediator.md) |
| `Pipeline` | Pipeline | [Pipeline](17-pipeline.md) |
| `Errors` | Exceptions | [Errores de dominio](19-errores.md) |
| `Registry` | Service Provider auto-discovery | [Monolito modular](06-monolito-modular.md) |
| `Logging` | Logging (Monolog) | [Logging](18-logging.md) |
| `Clock` | — (reloj inyectable, estilo `Carbon::setTestNow()`) | — |

!!! info "Regla de capas"
    `Core` nunca importa de `Modules`, y `Core` **nunca importa la capa web** (FastAPI,
    Starlette, auth…). El correo **sí** vive en `Core` (`Core/Mail`, con Jinja para las
    plantillas e `i18nice` para el i18n de los correos): es worker-side. Ambas reglas las
    fuerza `import-linter` en CI.

## Siguiente paso

[Ciclo de vida](05-ciclo-de-vida.md).
