# Introducción

**tequio** es un microframework de Python 3.14 para construir **servicios worker-side**:
daemons, pipelines de datos (ETL), monitores y tareas en segundo plano. No reinventa
nada: ensambla piezas maduras del ecosistema Python detrás de una estructura opinada y un
kernel reutilizable, **estilo milpa**.

| Pieza | Para qué |
|-------|----------|
| **Celery** | jobs en background y crons |
| **SQLAlchemy 2.0** | acceso a datos (agnóstico del motor) |
| **Alembic** | migraciones de esquema |
| **Typer** | consola (`jornal`, el "artisan") |
| **Loguru** | logging unificado (consola + archivo) |

!!! info "tequio (del náhuatl *tequitl*, trabajo)"
    Faena colectiva donde la comunidad ejecuta las tareas que benefician a todos. Aquí:
    tus workers.

## De dónde viene tequio

tequio **nació extrayendo el lado worker de [milpa](https://github.com/calcifux/milpa)**.
milpa es un framework de monolitos modulares con capa HTTP (FastAPI), auth, vistas y un
frontend Vite. Pero muchos servicios **no sirven páginas ni API**: un ETL nocturno, un
monitor de flota, un daemon que consume una cola. Para esos, toda la maquinaria web es
peso muerto.

tequio es ese núcleo worker-side **solo**: jobs, crons, eventos/observers, los patrones
estilo milpa (Mediator, Pipeline), base de datos, logging y **correo** (porque muchos
crons y jobs terminan mandando un correo) — **sin** la capa web. El contrato de capas
(forzado por `import-linter` en CI) garantiza que FastAPI, los endpoints o el auth **no
se vuelvan a colar** al core.

### Qué trae tequio / qué vive en milpa

| Capacidad | tequio | milpa |
|-----------|:------:|:-----:|
| Jobs en background (`@job`) | ✅ | ✅ |
| Crons declarativos (`@cron_task`) | ✅ | ✅ |
| Eventos y Observers | ✅ | ✅ |
| Mediator (command bus) | ✅ | ✅ |
| Pipeline | ✅ | ✅ |
| Base de datos (SQLAlchemy + Alembic) | ✅ | ✅ |
| Repositorios, seeders, factories | ✅ | ✅ |
| Logging (Loguru) | ✅ | ✅ |
| CLI (Typer) | ✅ | ✅ |
| Correo (Mailables) | ✅ | ✅ |
| i18n de los correos | ✅ | ✅ |
| HTTP / API (FastAPI) | ❌ | ✅ |
| Autenticación (Passport) | ❌ | ✅ |
| Vistas / Vite / microfrontends | ❌ | ✅ |
| i18n de la UI | ❌ | ✅ |

!!! note "Las features web viven en milpa"
    Donde necesites servir páginas o una API, eso es trabajo de
    [milpa](https://github.com/calcifux/milpa). tequio se detiene en el borde del worker.

### ¿Cuál elijo?

- **¿Sirves páginas o una API HTTP?** → **milpa**. Trae FastAPI, vistas, auth y el
  frontend Vite conectados.
- **¿Es un daemon, un ETL, un monitor, un consumidor de cola, un cron?** → **tequio**.
  Sin capa web encima (pero **sí** con correo, que vuelve al worker).

Ambos comparten el mismo ADN ("estilo milpa"), el mismo launcher (`./jornal`, a
propósito el mismo nombre) y los mismos patrones, así que migrar conceptos entre uno y
otro es directo.

## Filosofía

### El kernel es el framework

Todo lo genérico y reutilizable vive en `tequio/Core`. Lo específico de tu proyecto vive
**fuera** de `Core`:

- `app/Modules/<Nombre>/` — tus features (jobs, crons, eventos, servicios, comandos).
- `app/Models/` — tus modelos SQLAlchemy.
- `app/Console/Commands/` — tus comandos generales de consola.

### Convención sobre configuración

El framework **descubre y conecta solo** lo que sueltas dentro de un módulo (el discovery
importa **todo el árbol** del módulo, así que el encarpetado es libre):

- Sueltas un `@job` en tu módulo (el demo lo pone en `Jobs/ExportNotesJob.py`) → el worker lo puede ejecutar.
- Sueltas un `@cron_task` en tu módulo (el demo, en `Crons/DailyDigestCron.py`) → el scheduler lo agenda.
- Sueltas un `@console_command` bajo `Modules/X/Console/Commands/` → `jornal` lo expone.
- Sueltas un modelo en `app/Models/` → SQLAlchemy lo registra.

No hay un archivo central que editar para "registrar" cada cosa. (Ver
[Monolito modular](06-monolito-modular.md).)

### Módulos independientes

Los módulos **no se importan entre sí**. Lo fuerza `import-linter` como contrato de CI.
Cada módulo es un microservicio en potencia: se puede extraer sin desenredar imports
cruzados. El kernel (`Core`) tampoco depende de los módulos.

### Persistencia estilo Spring Data

Repositorios tipados `Repository[Model, Id]` con CRUD heredado; escrituras en servicios
`@transactional` (commit/rollback automático). La sesión es **ambiente** (contextvar), no
se inyecta por constructor. (Ver
[Repositorios y transacciones](10-repositorios-y-transacciones.md).)

## Calidad forzada

El proyecto trae cinco guardrails que corren en local y en CI:

```bash
uv run ruff check .        # lint
uv run ruff format .       # formato
uv run mypy                # tipos (estricto)
uv run lint-imports        # fronteras entre capas y módulos
uv run pytest              # tests (sin BD)
```

## Siguiente paso

[Instalación](02-instalacion.md).
