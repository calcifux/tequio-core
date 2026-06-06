# Documentación de tequio

**tequio** es la extracción **worker-side** de [**milpa**](https://github.com/calcifux/milpa):
un núcleo de **Python 3.14** para servicios que NO sirven HTTP —daemons, pipelines de datos,
monitores, ETLs, cron-jobs— con el mismo estilo y buena parte del mismo kernel. Junta Celery
(tareas/crons), SQLAlchemy 2.0 (datos) y Typer (consola) detrás de una estructura opinada y un
kernel reutilizable.

Esta documentación está pensada para leerse en orden, como la de Laravel: empieza por
"Primeros pasos", luego "Arquitectura", y profundiza por tema.

> Filosofía en una línea: el kernel (`tequio/Core`) es el framework; lo tuyo vive en
> `app/Modules`, `app/Models` y `app/Console`. Tú escribes features; el framework descubre y
> conecta solo.

!!! note "¿tequio o milpa?"
    Si tu servicio sirve páginas o API REST, quieres **milpa** (trae Http, Auth, Views/Vite e
    i18n de la UI *además* de todo lo de tequio). Si solo procesa trabajo en background contra
    una base de datos, **tequio** te deja más ligero — con **correo** incluido, porque vuelve al
    worker. A lo largo de estas docs, lo que vive en milpa y no aquí se anota con un *"esto vive
    en milpa"* y su enlace.

## Primeros pasos

1. [Introducción](01-introduccion.md) — qué es tequio, su filosofía y qué se quedó en milpa.
2. [Instalación](02-instalacion.md) — `uv` o pip, drivers de BD, broker.
3. [Configuración](03-configuracion.md) — `.env` y la clase `Settings`.
4. [Estructura de directorios](04-estructura-directorios.md) — qué hay y dónde.
5. [Ciclo de vida](05-ciclo-de-vida.md) — arranque de la consola, Celery y el discovery.

## Arquitectura

6. [Monolito modular](06-monolito-modular.md) — Core vs Modules, auto-discovery, fronteras (`import-linter`).
7. [Errores de dominio](19-errores.md) — `DomainError` y el borde de error del CLI.

## Consola

8. [`jornal`](07-consola-jornal.md) — comandos, grupos, crear los tuyos.

## Base de datos

9. [Base de datos](08-base-de-datos.md) — engine agnóstico, `DATABASE_URL`, zona horaria, migraciones Alembic.
10. [Modelos](09-modelos.md) — SQLAlchemy, auto-discovery, mixins (timestamps, soft delete).
11. [Repositorios y transacciones](10-repositorios-y-transacciones.md) — `Repository[Model, Id]`, `@transactional`.
12. [Filtrado y paginación](11-filtrado-y-paginacion.md) — DSL de filtrado + paginación.

## Background

13. [Jobs (`@job`)](12-jobs.md) — background on-demand, `.dispatch()`, `broker_guard`.
14. [Colas y tareas](13-colas-y-tareas.md) — Celery, broker-agnóstico, `queue work`.
15. [Programación (cron)](14-programacion-cron.md) — `@cron_task`, `schedule run/work`.

## Patrones (estilo milpa)

16. [Eventos y Observers](15-eventos-y-observers.md) — `dispatch` 1:N, broker-adaptive.
17. [Mediator (command bus)](16-mediator.md) — `@handles` / `send`, 1:1.
18. [Pipeline](17-pipeline.md) — pipeline modelo cebolla (estilo Laravel).

## Más

19. [Correo](20-correo.md) — Mailables, la facade `Mail`, drivers (log/SMTP), i18n de correos, Mailpit.
20. [Logging](18-logging.md) — Loguru, JSON, niveles.

---

## Mapa mental Laravel → tequio

| Laravel | tequio |
|---------|--------|
| `artisan` | `jornal` |
| `php artisan queue:work` | `jornal queue work` |
| `php artisan schedule:work` | `jornal schedule work` |
| `php artisan schedule:run` | `jornal schedule run` |
| `$schedule->command(...)->everyFiveMinutes()` | `@cron_task(schedule=...)` |
| `dispatch(new X)` / `Job` | `@job` + `.dispatch()` |
| Event / Listener | Event + `Observer` (auto-descubierto) |
| Eloquent Model | modelo SQLAlchemy (`app/Models`) |
| `$table->timestamps()` | `TimestampMixin` |
| `SoftDeletes` | soft-delete automático |
| Repository / Service | `Repository[Model, Id]` / service `@transactional` |
| `php artisan migrate` | `jornal migrate run` |
| `php artisan make:model Foo` | `jornal make model Foo` |
| `php artisan db:seed` | `jornal db seed` |
| `config()` / `.env` | `settings` / `.env` |
| Service Provider auto-discovery | auto-discovery por convención (Registry) |
