# Changelog

Todos los cambios notables de **tequio** se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Versionado Semántico](https://semver.org/lang/es/). En `0.x` la API puede cambiar entre minors.

## [Unreleased]

## [0.1.4] - 2026-06-07

**Ciudadanía en un broker compartido.** El origen es un incidente real: en la mega-red **aqua**
del dueño, varias apps tequio/milpa apuntaban al **mismo redis db** y empezaron a robarse tasks.
Dos fallos a la vez — una task que la app vecina **no conoce** se descarta (`KeyError` =
**corrida perdida**), y `mail.send`/`events.handle` (registradas con el mismo nombre en TODAS
las apps) se ejecutan **cruzadas en silencio**, con la config equivocada (el correo de una app
sale por el SMTP de otra, sin un solo error). El db-por-app mitiga, pero muere en **Redis
Cluster** (solo expone el db 0). Más un segundo hoyo destapado de paso: los defaults del layout
apuntaban al paquete del framework, así que una instalación **sin `.env`** auto-descubría el
Demo EMPAQUETADO y agendaba su cron en el broker del usuario.

### Added

- **`QUEUE_NAMESPACE`** (env; default `""` = comportamiento actual, 100% retrocompatible): prefijo
  de colas para convivir en un broker compartido. Con un valor, la cola por defecto pasa a
  `<ns>.celery` (vía `task_default_queue`, lo que aísla TODO despacho **sin** `queue=` explícito:
  `events.handle`, `Mail.queue` sin cola, jobs/crons a la default) y las colas con nombre se
  prefijan `<ns>.<cola>`. Un resolvedor único — `qualified_queue(name)` en
  `Core/CeleryApp/Dispatch.py`, exportado en `Core/CeleryApp` — aplica el prefijo en UN solo
  lugar; por él pasa cada call-site con `queue=` explícito (`enqueue_mail`, `Job.dispatch`, el
  despacho de crons en `schedule run`, las entradas del beat y el worker `queue work --queue a,b`,
  que califica **cada** nombre de la lista). A diferencia del db-por-app, **sobrevive en Redis
  Cluster** (todo vive en el db 0). El lock anti-overlapping de los crons también se namespacea:
  `cron-lock:<name>` → `cron-lock:<ns>:<name>` (sin ns, la key actual intacta).

### Changed

- **Los defaults del layout apuntan al usuario, no al framework**: `MODULES_PACKAGE`,
  `MODELS_PACKAGE` y `APP_COMMANDS_PACKAGE` pasan de `tequio.*` a `app.Modules` / `app.Models` /
  `app.Console.Commands` (el layout que genera `tequio new`). Así una instalación **sin `.env`
  configurado** ya NO auto-descubre el Demo EMPAQUETADO del framework (era la causa de que un
  usuario terminara agendando el cron del Demo en SU broker). El dev que trabaja DENTRO de este
  repo (código en `src/tequio`, no en `app/`) re-apunta los tres paquetes a `tequio.*` en su
  `.env`; en la suite, `Tests/conftest.py` ya hace ese `setdefault` (patrón del `LOG_DIR`
  existente) y fija `APP_ENV=local`.
- **El cron del Demo gatea por entorno**: `DailyDigestCron` gana `environments=("local",
  "development")` — cinturón extra para que, ni apuntando `MODULES_PACKAGE` al Demo a propósito,
  el digest se agende en producción.
- **Smoke del CI**: con el default nuevo, un wheel limpio + `tequio list` ya no descubre el Demo
  (es el comportamiento CORRECTO); el smoke verifica los comandos del framework, no los del demo.

### Tests

- Cobertura nueva (sin BD): el resolvedor `qualified_queue` (passthrough sin ns, `None`→`None`,
  prefijo con ns), la `task_default_queue` del `celery_app` (intacta sin ns, `<ns>.celery` con
  ns), `enqueue_mail`/`Job.dispatch`/el despacho de cron/las opciones del beat califican su cola,
  el CLI mapea la lista `--queue`, la key del lock con/sin ns, y el default vacío de
  `queue_namespace`.

## [0.1.3] - 2026-06-07

Paridad con milpa 0.6.0 — la primera cosecha del **drift-guard** (la herramienta interna
que compara el kernel compartido entre hermanos): 17 archivos huérfanos detectados en su
primera corrida, repartidos entre ambos lados.

### Added

- **`schedule work --schedule-file <ruta>`**: reubica el archivo de estado del beat (`-s` de
  Celery; default `./celerybeat-schedule` del CWD). En docker con el repo montado, apúntalo a
  un volumen escribible (p. ej. `/tmp/celerybeat-schedule`).
- **`TEQUIO_ENV_FILE`**: el `.env` deja de estar clavado al CWD — un beat en contenedor apunta
  la variable a la ruta real y se acabaron los symlinks.
- **`auto_session` en la fachada** (`from tequio import auto_session`): el hermano idiomático
  de `transactional`/`session_scope` faltaba en el import plano.

### Fixed

- **Error accionable del lock store** *(de milpa 0.6.0)*: si `without_overlapping` no puede
  conectar al LOCK store, el cron truena con instrucción (el default es un redis LOCAL; en
  docker configura `LOCK_URL=redis://<host>`) en vez de un stacktrace de redis.
- Prosa restaurada en `Events/` (las referencias a `Mail.queue` volvieron: tequio ya tiene
  correo desde 0.1.x y los docstrings seguían esquivándolo).

## [0.1.2] - 2026-06-06

### Añadido

- **Fachada pública perezosa** (`from tequio import job, cron_task, celery_app, …`): la API
  estable en un import plano (PEP 562). `import tequio` a secas queda SIN efectos colaterales
  —no instancia Celery ni lee el `.env` hasta que pides un símbolo— y las rutas profundas
  (`from tequio.Core.Jobs import job`) siguen siendo válidas.
- **`py.typed`** (PEP 561): el paquete es mypy-strict pero no publicaba sus tipos; ahora los
  consumidores reciben los type hints completos en mypy y el IDE.
- **Metadata de PyPI**: trove classifiers, keywords y `[project.urls]` — la página del paquete
  ahora tiene links a repo, docs, changelog e issues, y es filtrable por classifier.

### Corregido

- **El sdist filtraba archivos del IDE** (`.idea/` con rutas locales y config de DataGrip):
  `.idea/` no estaba en el `.gitignore` raíz y hatchling arma el sdist según ese archivo.
  Doble candado: `.gitignore` actualizado **y** allowlist explícita
  `[tool.hatch.build.targets.sdist]` (el sdist ahora solo lleva `src/tequio`, README, LICENSE
  y CHANGELOG — fuera también `Tests/`, `documentation/`, `uv.lock` y demás cruft de dev).
  **El release 0.1.1 queda yanked en PyPI por esto.**
- Skeleton: el `pyproject.toml.tmpl` que genera `tequio new` aún decía que tequio-core "no
  está publicado en PyPI" (lo está desde 0.1.0).

## [0.1.1] - 2026-06-06

### Corregido

- **PyPI mostraba la página del paquete sin descripción**: faltaba `readme = "README.md"`
  en `[project]` (la metadata de una versión ya publicada no se puede editar; de ahí este
  release). La página de `tequio-core` ahora muestra el README completo.
- Docs/README: eliminadas las notas de "aún no publicado en PyPI" — `tequio-core` vive en
  PyPI desde 0.1.0.

## [0.1.0] - 2026-06-06

**Nacimiento de tequio**: la extracción **worker-side** de [milpa](https://github.com/calcifux/milpa)
`0.4.0`. El mismo estilo y el mismo kernel reutilizable (`Core`), pero **sin la capa web** —para
servicios de Python que NO sirven páginas ni API (daemons, pipelines, monitores, ETLs, cron-jobs)
y solo necesitan **trabajo en segundo plano + base de datos + consola**, con **correo** que vuelve
al worker. Un contrato de `import-linter` garantiza que la capa web nunca se vuelva a colar al core.

Forma tradicional vs estilo milpa: la forma tradicional arrastra todo el framework web (FastAPI,
auth, pipeline de assets) aunque el servicio nunca sirva HTTP; estilo milpa el worker baja de peso
quedándose solo con lo que de verdad usa (Celery + SQLAlchemy + Typer + correo), y el guardrail de
fronteras lo mantiene así.

### Added

#### Lo que vino de milpa 0.4.0 (worker-side)

- **Background** — `@job` (on-demand, `.dispatch()`, con `broker_guard` que traduce el broker caído
  en un error accionable) y `@cron_task` (agendado, anti-overlap con lock en Redis y gate por
  `APP_ENV`), separados a propósito (job ≠ cron). Celery broker-agnóstico (`BROKER_URL`).
- **Patrones estilo milpa** (OPT-IN, auto-descubribles) — `Events`/`Observers` (1:N, transporte
  adaptativo: worker si hay broker, si no síncrono), `Mediator` (command bus 1:1, `@handles`/`send`)
  y `Pipeline` (modelo cebolla). Patrones que un arquitecto puede sugerir, no impuestos.
- **Datos estilo Spring Data** — `Repository[Model, Id]` tipado, `@transactional`,
  `current_session`, `Factory`/`Seeder` (con Faker), soft-delete y timestamps automáticos; engine
  **agnóstico del motor** (se elige por `DATABASE_URL`, default `sqlite` zero-config), migraciones
  **Alembic** motor-agnósticas.
- **Errores que NUNCA fallan en silencio** — el CLI rinde un `DomainError` (esperado) como mensaje
  accionable + su código (sin traceback crudo) y deja el traceback completo de un error inesperado
  en el log.
- **Consola estilo artisan** — kernel Typer con descubrimiento automático de comandos (Core +
  generales del proyecto + módulos): `queue work`, `schedule work`/`run`, `migrate`, `db seed`,
  `make …`, salida en tabla rich.
- **Logging** — Loguru configurado (stderr conciso sin fuga de valores + archivo rotativo);
  `LOG_JSON=true` agrega `logs/app.jsonl` (JSON Lines) para Loki/Grafana.
- **Config tipada** — `Settings` (pydantic-settings) lee el `.env`; la infraestructura sin default
  (obligatoria) falla claro si falta.
- **Reloj inyectable** (`Core/Clock`) — `SystemClock` / `FixedClock` (= `Carbon::setTestNow`) para
  congelar el tiempo en tests, estilo `java.time.Clock` de Spring.

#### Lo propio de tequio

- **Correo worker-side** (`Core/Mail`) — Mailables estilo Laravel (`Mail.send` / `Mail.queue`),
  drivers (`smtp`/`log`/`null`), adjuntos por bytes o archivo y logo por CID. Vuelve al worker
  porque muchísimos crons y jobs terminan mandando correo (justo el caso del `DailyDigestCron`).
- **TemplateEngine e i18n de correos worker-side** (`Core/View/TemplateEngine.py`, `Core/Translate`)
  — los correos se renderizan con Jinja2 y se traducen con `i18nice`, todo worker-side; `jinja2` e
  `i18n` quedan permitidos por el contrato de fronteras (lo prohibido es la capa HTTP/Auth/frontend,
  no el correo).
- **Cola `emails` por convención** — los correos se encolan a la cola `emails`
  (`queue work --queue emails`), el equivalente del `->onQueue('emails')` de Laravel; con
  `MAIL_DRIVER=log` (default dev) el MIME se vuelca al log sin SMTP, y el `docker-compose.yml` trae
  Mailpit para verlos en una UI.
- **`queue work --pool`** — opción para elegir el pool de Celery (`prefork`/`solo`/`threads`/
  `gevent`); en **Windows**, si se omite, cae a `solo` automáticamente (el prefork de billiard no es
  confiable ahí).
- **Encarpetado libre con discovery recursivo** — el discovery importa **todo el árbol** de cada
  módulo (`import_submodules(..., recursive=True)`), así organizas tu app como quieras: la pieza se
  descubre mientras lleve su decorador o herede de su base. La única convención con peso es
  `Console/Commands/`. El guardrail `test_FreeLayoutDiscovery` fija esta libertad.
- **El beat agenda los `@cron_task`** — `collect_beat_schedule()` (en el `Registry`) **fusiona** dos
  fuentes para el calendario del beat: (1) cada `@cron_task(schedule=…)` auto-descubierto —su
  expresión cron convertida a `celery.schedules.crontab`— y (2) los `beat_schedule` declarados en
  `Console/Kernel.py` (vía declarativa, **con precedencia** en colisiones de nombre). Así
  `schedule work` (el beat) agenda los `@cron_task` **sin** escribir un `Kernel.py`. El conversor
  cron-string → `crontab` exige **exactamente 5 campos**; si no, falla con un error claro (no agenda
  mal en silencio). Los gates de ejecución (anti-overlap y `environments`) siguen viviendo en
  `@cron_task` al ejecutar; el beat solo agenda. (Decisión consciente: este comportamiento **diverge
  de milpa**, que solo agendaba lo declarado en `Console/Kernel.py`.)
- **Demo `Notes`** (`tequio new --demo`) — módulo de referencia corrible (notas, worker-side) que
  ejercita TODO el stack: `@job`, `@cron_task` (un digest diario que **manda correo**),
  eventos→observer (1:N), Mediator (1:1), Pipeline de limpieza y Mailables (i18n de correos), más
  seeders/factories con Faker. Corre sobre SQLite sin levantar infraestructura. La nota es
  deliberadamente mínima (`title`/`body`/`archived`): tequio no tiene Auth ni usuarios (eso vive en
  milpa), así que la nota no tiene dueño.
- **Scaffolder `tequio new <app> [--demo]`** — genera un proyecto listo para correr desde un
  skeleton embebido (estilo `laravel new`); el paquete se llama `tequio-core` en PyPI pero el import
  y el comando siguen siendo `tequio`. `--demo` materializa el módulo Notes; sin él, un módulo
  `Hello` mínimo.
- **Tres contratos `import-linter`** — (1) `forbidden`: `tequio.Core` **NO** depende de la capa web
  (fastapi/starlette/uvicorn/slowapi/httpx/itsdangerous/pwdlib/jwt) —el contrato distintivo de
  tequio—; (2) `forbidden`: el shared kernel (`Core`/`Models`/`Dictionaries`) no importa
  `Modules`; (3) `independence`: los módulos no se importan entre sí.
- **Documentación completa** (mkdocs) — guía estilo Laravel en español: instalación, configuración,
  ciclo de vida (del **worker**, sin request), monolito modular, consola (`jornal`), base de datos,
  background (jobs, colas, cron + el reloj), los patrones estilo milpa, correo, errores de dominio y
  logging. Cada feature contrasta la *forma tradicional* vs *estilo milpa* y se demuestra ejecutable
  en el módulo Demo.

### Excluido (vive en milpa)

- **Http/FastAPI, Auth** (RBAC/ABAC, JWT/sesión, Passport), **Views/Vite** (frontend,
  microfrontends, PWA) e **i18n de la UI**. tequio **sí** trae correo (Mailables + i18n de correos)
  porque vuelve al worker. Si tu servicio necesita algo de lo excluido, usa
  [milpa](https://github.com/calcifux/milpa).

### Notas

- Todo es **síncrono** (SQLAlchemy + Celery). Los tests corren **sin base de datos** (fakes +
  monkeypatch) y el toolchain de gates es ruff + mypy strict + import-linter + pytest.

[Unreleased]: https://github.com/calcifux/tequio-core/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/calcifux/tequio-core/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/calcifux/tequio-core/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/calcifux/tequio-core/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/calcifux/tequio-core/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/calcifux/tequio-core/releases/tag/v0.1.0
