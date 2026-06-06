# tequio 🤝

[![CI](https://github.com/calcifux/tequio-core/actions/workflows/ci.yml/badge.svg)](https://github.com/calcifux/tequio-core/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.14+-3776AB?logo=python&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-37814A?logo=celery&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00)
![Typer](https://img.shields.io/badge/CLI-Typer-009688)
![uv](https://img.shields.io/badge/deps-uv-DE5FE9)
![Ruff](https://img.shields.io/badge/lint-ruff-261230?logo=ruff&logoColor=white)
![Mypy](https://img.shields.io/badge/types-mypy_strict-2A6DB2)
![License](https://img.shields.io/badge/license-MIT-blue)

> **tequio** (del náhuatl *tequitl*, trabajo): faena colectiva donde la comunidad ejecuta las
> tareas que benefician a todos. Aquí, tus **workers**.

**tequio** es la extracción **worker-side** de [**milpa**](https://github.com/calcifux/milpa):
el mismo estilo y el mismo kernel reutilizable, pero **sin la capa web**. Para servicios de
**Python 3.14** que NO sirven páginas ni API —daemons, pipelines de datos, monitores, ETLs,
cron-jobs— y que solo necesitan **trabajo en segundo plano + base de datos + consola**. Junta
tres piezas maduras detrás de una estructura opinada:

> **Celery** para tareas/crons · **SQLAlchemy 2.0** para datos · **Typer** para la consola.

Pensado para dos cosas: **arrancar workers nuevos** sin re-decidir la arquitectura cada vez, y
**bajar de peso** un servicio que no necesita HTTP (sin arrastrar FastAPI, auth ni un pipeline de
assets que nunca vas a usar). Un contrato de `import-linter` garantiza que la capa web nunca se
vuelva a colar al core.

---

## 🌽 tequio vs milpa — ¿cuál uso?

Son el **mismo estilo** y comparten el grueso del kernel (`Core`). La diferencia es **una sola
pregunta**: ¿tu servicio sirve HTTP?

| | **tequio** (este repo) | **milpa** |
|---|---|---|
| Para | workers, crons, pipelines, ETLs, daemons | apps y APIs web (+ todo lo de tequio) |
| Trae | Jobs, Cron, Events/Observers, Mediator, Pipeline, BD (SQLAlchemy+Alembic), Logging, Console, **Mail** (+ i18n de correos) | **todo lo de tequio** + Http, Auth, Views/Vite, i18n de UI |
| NO trae | Http/FastAPI, Auth, Views/Vite, i18n de UI | — |
| Launcher | `./jornal` | `./jornal` (mismo nombre, a propósito) |
| Import / CLI | `import tequio` · `tequio` | `import milpa` · `milpa` |

> Regla de bolsillo: **si tu servicio sirve páginas o API REST, quieres milpa.** Si solo procesa
> trabajo en background contra una base de datos, **tequio** te deja más ligero (con **correo**
> incluido, que vuelve al worker). Lo que vive en milpa y no aquí (HTTP, auth, vistas, frontend
> Vite, i18n de UI) se anota a lo largo de estas docs con un *"esto vive en milpa"* y su enlace.

---

## 🚀 Quickstart

`tequio` se instala como cualquier paquete y trae el comando `tequio new`, que genera un proyecto
listo para correr (estilo `laravel new` / `django-admin startproject`):

```bash
# 1) instala el paquete (de forma aislada con uv, o como dependencia con pip)
uv tool install tequio-core    # o:  pipx install tequio-core  ·  pip install tequio-core
# El paquete se llama `tequio-core` en PyPI (porque `tequio` puede chocar con otro proyecto), pero
# el comando de consola y el import SIGUEN siendo `tequio`: `tequio new …` / `import tequio`.
#
# ⚠️ tequio-core AÚN NO está publicado en PyPI. Mientras tanto, instálalo desde el repo:
#     uv tool install "git+https://github.com/calcifux/tequio-core"
#     # o, clonado en local:  uv tool install /ruta/a/tequio-core

# 2) crea un proyecto CON el demo de notas (jobs/crons/observers, mediator, pipeline, seeder Faker)
tequio new pulso --demo
cd pulso

# 3) instálalo, migra, siembra y arranca el worker
uv sync                                          # instala tequio + deps + faker (dev)
python jornal migrate run                        # aplica la migración que ya trae el demo (sqlite, zero-config)
python jornal db seed                            # puebla notas demo (DemoSeeder, con Faker)
python jornal queue work                         # 👉 arranca el worker (procesa los @job)
```

Sin `--demo` obtienes un esqueleto limpio (un módulo `Hello` mínimo) para empezar de cero; ahí los
siguientes pasos son simplemente `uv sync` y `python jornal list`.

> **`jornal`** es el "artisan" de tequio (lo genera el scaffolder en la raíz del proyecto), con el
> **mismo nombre** que el de milpa a propósito: `queue work`, `schedule work`, `make model|job|…`,
> `migrate make|run`, `db seed`, … Ve todo con `python jornal list`.

---

## ✨ Características

Todo es **OPT-IN** y auto-descubrible (no estorba si no lo usas):

- **Background** — `@job` (on-demand, `.dispatch()`, con `broker_guard`) y `@cron_task` (agendado,
  anti-overlap con lock en Redis y gate por `APP_ENV`), separados a propósito (job ≠ cron).
- **Patrones estilo milpa** — `Events`/`Observers` (1:N, transporte adaptativo: worker si hay
  broker, si no síncrono), `Mediator` (command bus 1:1, `@handles`/`send`) y `Pipeline` (modelo
  cebolla). Patrones ya probados que un arquitecto puede sugerir, no impuestos.
- **Datos estilo Spring Data** — `Repository[Model, Id]` tipado, `@transactional`, `current_session`,
  `Factory`/`Seeder` (con Faker), soft-delete y timestamps automáticos; engine **agnóstico del
  motor** (se elige por `DATABASE_URL`), migraciones **Alembic** motor-agnósticas.
- **Errores que NUNCA fallan en silencio** — el CLI rinde errores limpios: un `DomainError`
  (esperado) sale como mensaje accionable + su código, sin traceback crudo ni fuga de valores; uno
  inesperado deja su traceback completo en el log (observable a las 3am).
- **Consola estilo artisan** — kernel Typer con descubrimiento automático de comandos (Core +
  generales del proyecto + módulos): `queue work`, `schedule work`/`run`, `migrate`, `db seed`,
  `make …`. Agregar un comando es solo crear su archivo.
- **Correo** — Mailables estilo Laravel (`Mail.send` / `Mail.queue`), drivers (`smtp`/`log`/`null`),
  adjuntos por bytes o archivo, logo por CID e i18n de los correos (`i18nice`). Vuelve al worker
  porque muchos crons y jobs terminan mandando correo; por convención los correos van a la cola
  **`emails`** (`queue work --queue emails`), y con `MAIL_DRIVER=log` (default dev) el MIME se
  vuelca al log sin SMTP, mientras el `docker-compose.yml` trae Mailpit para verlos en una UI.
- **Logging** — Loguru configurado (stderr concisa sin fuga de valores en prod + archivo);
  `LOG_JSON=true` agrega `logs/app.jsonl` (JSON Lines) para Loki/Grafana.
- **Config tipada** — `Settings` (pydantic-settings) lee el `.env`; infraestructura sin default
  (obligatoria) para fallar claro si falta.

> **Lo que NO trae tequio (vive en milpa):** Http/FastAPI, Auth (RBAC/ABAC, JWT/sesión, Passport),
> Views/Vite (frontend, microfrontends, PWA) e i18n de la UI. **Sí** trae **Mail** (Mailables,
> i18n de correos) porque vuelve al worker. Si tu servicio necesita algo de lo que no trae, usa
> [milpa](https://github.com/calcifux/milpa).

---

## 🎮 El demo (`tequio new --demo`)

`--demo` materializa un módulo de referencia **corrible** (notas, **worker-side**) que ejercita TODO
el stack y sirve de plantilla viva: `@job`, `@cron_task` (con un **digest que manda correo**),
**eventos→observer** (1:N), el **Mediator** (1:1), el **Pipeline** de limpieza y **Mailables**
(i18n de correos), más **seeders/factories con Faker**. Corre sobre **SQLite** sin levantar
infraestructura. El modelo `Note` es **deliberadamente mínimo** (`title`/`body`/`archived`):
tequio no tiene Auth ni tabla de usuarios, así que la nota **no tiene dueño** (eso vive en milpa).

```bash
cd pulso                                 # el proyecto que generó `tequio new pulso --demo`
python jornal migrate run                # aplica la migración que ya trae el demo (Alembic)
python jornal db seed                    # 23 notas con Faker + 1 nota a mano ("Idea de Beto")
python jornal queue work                 # arranca el worker: procesa los @job que despaches
python jornal schedule work              # (en otra terminal) el beat: agenda y dispara los @cron_task
```

### Pruébala en 2 minutos (sin docker, sin SMTP)

Todo corre sobre el sqlite local y el driver `log` (el default del `.env` generado):

```bash
python jornal list                  # los comandos del demo ya montados: `demo archive`, `hello greet`…
python jornal demo archive 1        # archiva la nota 1 vía Mediator → "Nota 1 archivada (archived=True)"

# El cron del digest, disparado a mano (sin esperar al beat). Con el broker apuntando a un
# puerto muerto, Mail.queue cae a su fallback síncrono y el driver log vuelca el MIME completo:
BROKER_URL=redis://127.0.0.1:1/0 python -c \
  "from app.Modules.Demo.Crons.DailyDigestCron import daily_digest; daily_digest()"
# → Subject: Resumen diario: 24 notas en total  (+ HTML renderizado por jinja y logo embebido)
```

¿Quieres verlo con infraestructura real? `docker compose up -d` (redis + mailpit), pon
`MAIL_DRIVER=smtp` en tu `.env` y corre el flujo completo: `python jornal queue work --queue
emails,celery` en una terminal y `python jornal schedule work` en otra (el beat **ya agenda** el
digest solo, sin `Kernel.py`; dispara a las 08:00 según su `schedule`). Para no esperar a esa
hora, despáchalo a mano contra el broker real —`python -c "from app.Modules.Demo.Crons.DailyDigestCron import daily_digest; daily_digest.delay()"`—
y el correo llega a la UI de mailpit en <http://localhost:8025>.

- **Jobs** (`@job`): despáchalos desde tu código con `.dispatch()` — el worker (`queue work`) los
  ejecuta en background; si el broker cae, `broker_guard` da un error limpio en vez de tragárselo.
- **Crons** (`@cron_task`): el beat (`schedule work`) **los agenda solo** (descubre cada
  `@cron_task(schedule=…)` y arma su calendario, sin `Kernel.py`) y los dispara según su
  `schedule`, con anti-overlap (lock) y gate por `APP_ENV` al ejecutar. El demo trae un
  **digest diario** que manda un correo:
  lo encola a la cola **`emails`** (`queue work --queue emails`), con fallback síncrono si el broker
  no está; con `MAIL_DRIVER=log` (default dev) el correo se vuelca al log sin SMTP.
- **Eventos / Mediator / Pipeline:** al crear una nota se emite un evento que un **Observer**
  (`LogNoteCreated`) loguea; archivar una nota (`demo archive <note_id>`) es un comando del
  **Mediator**; el contenido pasa por un **Pipeline** de limpieza antes de guardarse.

> Cada feature tiene su página en el [manual](https://calcifux.github.io/tequio-core/) y se demuestra
> ejecutable en el módulo Demo (contrastando la *forma tradicional* vs *estilo milpa*).

---

## 📖 Documentación

La guía completa estilo Laravel se publica en **<https://calcifux.github.io/tequio-core/>**:
instalación, configuración, estructura de directorios, ciclo de vida, monolito modular, consola
(`jornal`), base de datos (modelos, repositorios, filtrado/paginación), **background** (jobs, colas,
cron), los **patrones estilo milpa** (eventos/observers, mediator, pipeline), errores de dominio y
logging.

---

## 🗂️ Estructura de un proyecto tequio

`tequio new` genera un proyecto donde TÚ trabajas en `app/`, y `tequio` (el framework, instalado
como paquete) aporta el kernel `tequio.Core`:

```
pulso/
  app/
    Modules/
      Demo/          # con --demo: módulo de referencia (notas + TODOS los patrones)
      Hello/         # sin --demo: un módulo mínimo de ejemplo
    Models/          # modelos SQLAlchemy (auto-discovery)
    Console/         # comandos de consola generales del proyecto
  migrations/        # revisiones Alembic (motor-agnóstico)
  jornal             # consola (artisan) del proyecto
  docker-compose.yml # SOLO infra de dev: redis (broker/lock) + mailpit (ver correos)
  .env               # configuración (DATABASE_URL, BROKER_URL, MODULES_PACKAGE, …)
  pyproject.toml     # depende de `tequio-core`
```

El **kernel** que aporta el paquete (`tequio.Core`) es genérico y reutilizable: `Jobs` (`@job`),
`Cron` (`@cron_task`), `Events`/`Mediator`/`Pipeline`, `Database` (Repository, `@transactional`,
Filtering, Seeder/Factory, Migrations), `CeleryApp`, `Errors` (`DomainError`), `Logging`,
`Console` (kernel Typer). No tocas el kernel: el framework descubre tus modelos, módulos, comandos,
crons y seeders por convención (le dices DÓNDE vive tu código vía `.env`: `MODULES_PACKAGE`,
`MODELS_PACKAGE`, …).

> **El encarpetado dentro de un módulo es LIBRE.** El discovery importa **todo el árbol** de cada
> módulo, así que a tequio le da igual cómo organices tu app: usa la convención que producen los
> generadores `make:*` (una carpeta por concern, `Jobs/ExportNotesJob.py`,
> `Mail/DailyDigestMailable.py`, …) como hace el demo, o aplana todo en archivos sueltos
> (`Jobs.py`, `Handlers.py`, …) — la pieza se descubre mientras lleve su decorador o herede de su
> base. La única convención con peso es `Console/Commands/`, donde se automontan los
> `@console_command`. El guardrail `test_FreeLayoutDiscovery` fija esta libertad.

### Agregar un módulo

`tequio` no tiene un `make module` único: armas el módulo soltando sus piezas con los generadores
`make …`, que crean el archivo y su carpeta de convención propuesta (idempotentes, no sobrescriben);
de ahí puedes mover/aplanar los archivos como prefieras, el discovery los encuentra igual:

```bash
python jornal make job Facturacion EmitirTimbres     # app/Modules/Facturacion/Jobs/EmitirTimbres.py
python jornal make observer Facturacion FacturaEmitida
python jornal make handler Facturacion ArchivarFactura
python jornal make repository Facturacion Factura
python jornal make seeder Facturacion Facturas
```

El worker y el beat lo **descubren solos**; el `import-linter` garantiza que no se enrede con otros
módulos (cada módulo es un microservicio en potencia: se puede extraer sin desenredar imports
cruzados).

---

## ✅ Calidad

tequio trae los guardrails de fábrica; en el proyecto generado corres:

```bash
uv run pytest          # tests rápidos, SIN base de datos
uv run ruff check .    # lint           (ruff format . para formato)
uv run mypy            # tipos (estricto)
uv run lint-imports    # fronteras entre módulos (+ contrato "el Core NO depende de la capa web")
```

> `faker` es dependencia de **dev** (la usan factories/seeders para `jornal db seed`): viene en el
> grupo dev del proyecto, así que `uv sync` la trae; un `pip install tequio-core` "pelón" no la incluye.

---

## 🐘 Base de datos

El engine es **agnóstico del motor**; se elige con `DATABASE_URL`. Por default `sqlite` (zero-config,
viene en Python). Para otro motor instala su extra:

```bash
uv add "tequio-core[postgres]"   # PostgreSQL (psycopg v3, binario)
uv add "tequio-core[mysql]"      # MySQL / MariaDB (pymysql)
uv add "tequio-core[oracle]"     # Oracle (oracledb)
uv add "tequio-core[mssql]"      # SQL Server (pyodbc)
```

Las migraciones son **Alembic** (motor-agnósticas): `jornal migrate make -m "…"` autogenera la
revisión desde tus modelos, `migrate run` la aplica, `migrate status`/`rollback` para inspeccionar y
revertir, y `db fresh` recrea la BD desde cero (destructivo).

---

## 🌐 Colas / broker

El transporte de Celery es **agnóstico** (`BROKER_URL`): vacío => Redis local por default; también
RabbitMQ (`amqp://…`). Docker **solo** levanta infraestructura de dev (Redis y Mailpit para ver
los correos); la app corre en el host con `jornal queue work` / `jornal schedule work`. Los crons
se despachan estilo Laravel: una
línea en el crontab del SO llama `jornal schedule run` cada minuto, o corres el beat con
`jornal schedule work` (una sola instancia).

---

## Licencia

[MIT](LICENSE) © @Calcifux (Carlos Guillermo Reyes Ramiro)
