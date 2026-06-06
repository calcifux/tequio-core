# Contribuir a tequio

¡Gracias por tu interés en contribuir! Este documento explica cómo levantar el proyecto
en local, las convenciones que seguimos y cómo enviar un Pull Request con las mejores
probabilidades de merge.

> Si vas a tocar un subsistema, lee primero su página en
> [`documentation/`](documentation/README.md): ahí está el "cómo funciona".

## ¿Qué es tequio (y qué no)?

tequio es la **extracción worker-side** de [milpa](https://github.com/calcifux/milpa):
el núcleo de trabajo en segundo plano (jobs, crons, eventos/observers, Mediator, Pipeline,
BD con SQLAlchemy + Alembic, logging y CLI). **No** trae capa HTTP, Mail, Auth,
Views/Vite ni i18n: si tu servicio sirve páginas o API, eso vive en
[milpa](https://github.com/calcifux/milpa), no aquí.

## Inicio rápido

```bash
git clone https://github.com/calcifux/tequio-core.git
cd tequio-core
uv sync                     # crea el venv y resuelve deps (incluye las de dev)
cp .env.example .env        # ajusta lo que necesites (sqlite ya viene por default)
uv run pytest               # si la suite pasa, ya puedes desarrollar
```

Con `uv`, antepón `uv run` a los comandos; con el venv activo, omítelo. El launcher de
consola en la raíz es `jornal` (el mismo nombre que en milpa, a propósito).

> **¿Quieres ver algo funcionando ya?** Corre el demo (sqlite, sin infra de BD):
> ```bash
> uv run python jornal migrate make -m inicial && uv run python jornal migrate run
> uv run python jornal db seed          # puebla notas con Faker (DemoSeeder)
> uv run python jornal queue work       # arranca el worker (procesa los @job)
> ```
> Notes worker-side: jobs/crons/observers que escriben al log, Mediator, Pipeline,
> seeder con Faker. Para procesar la cola y el beat necesitas un broker (Redis); los
> flujos síncronos no lo tocan.

## Requisitos

- **Python 3.14+**
- **[uv](https://docs.astral.sh/uv/)** (recomendado) como gestor de entorno y deps
- **Docker NO** es necesario para los tests: son unitarios y **sin base de datos** (usan
  fakes y monkeypatch, no servicios vivos). Para correr la cola/beat de verdad hace falta
  un broker (Redis), no para contribuir/testear.
- **Git** con auth SSH o HTTPS a GitHub

## Estructura del repo

```
src/tequio/
  Core/          ← EL FRAMEWORK (kernel genérico worker-side, reutilizable)
  Models/        ← modelos SQLAlchemy compartidos (auto-discovery)
  Dictionaries/  ← constantes de dominio compartidas
  Modules/       ← los módulos del proyecto (independientes entre sí; Demo es el de referencia)
  Console/       ← commands GENERALES del proyecto (opcional)
Tests/           ← espeja src/tequio/ 1:1; tests unitarios sin BD
documentation/   ← guía estilo Laravel (sitio MkDocs Material)
jornal           ← entrypoint de consola en la raíz (el "artisan")
```

Detalle en [documentation/04-estructura-directorios.md](documentation/04-estructura-directorios.md).

## Las dos fronteras (no las rompas)

`import-linter` las fuerza en CI (ver `[tool.importlinter]` en `pyproject.toml`):

1. **tequio es worker-side**: `tequio.Core` **no** importa la capa web ni mail
   (`fastapi`, `starlette`, `uvicorn`, `jinja2`, `jwt`, `i18n`, …). Ese contrato evita
   que la capa HTTP/auth de milpa se vuelva a colar al núcleo.
2. **El kernel no depende de los módulos**: `tequio.Core` / `tequio.Models` /
   `tequio.Dictionaries` no importan `tequio.Modules`.
3. **Los módulos son independientes entre sí**: `tequio.Modules.A` no importa
   `tequio.Modules.B`.

Si dos módulos necesitan compartir algo, ese algo sube al kernel compartido. Ver
[documentation/06-monolito-modular.md](documentation/06-monolito-modular.md).

## Ramas y commits

- `main` siempre verde. No hagas push directo; abre un PR.
- Ramas de feature: `feat/cron-lock-timeout`, `fix/queue-retry-backoff`, `docs/install-guide`.
- [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`,
  `refactor:`, `test:`, `ci:`, `chore:`.

## Estilo de código

- Identificadores en **inglés**; comentarios y docstrings en **español**, explicando el
  *porqué* (no abreviar).
- Sin emojis en código/comentarios/docstrings.
- Tipos completos: `mypy` corre en modo **estricto** sobre `src/tequio` y `Tests/Core`.
- Un archivo por clase/responsabilidad (estilo Laravel/PascalCase en `src/tequio`).
- Formato e imports los maneja **Ruff** (no formatees a mano); cada archivo declara
  `from __future__ import annotations` (lo exige y autofixea Ruff).

## Guardrails (lo que valida CI)

Antes de abrir el PR, corre todo y déjalo verde. Son los **3 guardrails** (lint, tipos,
fronteras) + **tests** + **build**:

```bash
uv run ruff format .        # formato        | --check  solo verifica (modo CI)
uv run ruff check .         # lint           | --fix    arregla lo auto-arreglable
uv run mypy                 # tipos (estricto)
uv run lint-imports         # fronteras (worker-side + módulos)
uv run pytest               # tests (rápidos, sin BD)
uv build                    # empaqueta sdist + wheel (no se publica algo que no construye)
```

Todo de una:

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports && uv run pytest && uv build
```

## Contribuir al Core

tequio es un **framework**: las contribuciones van al **kernel** (`src/tequio/Core`), a sus
tests (`Tests/Core`) y a la documentación. **No** se trata de crear módulos de negocio
nuevos — eso lo hace cada proyecto que *usa* tequio, en su propio repo (con `tequio new`).
`src/tequio/Modules/Demo` es solo el módulo de **referencia/demo** (Notes worker-side):
tócalo únicamente para demostrar una capacidad del Core, no para meter features de dominio.

Al tocar el Core:

1. **Mantén el Core genérico.** Nada de dominio ni de un proyecto en particular (ni
   nombres, ni reglas de negocio): el kernel debe servir igual a cualquier servicio
   worker-side. Si dudas si algo es "del framework" o "de un proyecto", probablemente no
   va en Core.
2. **Respeta las fronteras**: `tequio.Core` no importa la capa web/mail ni los módulos (el
   discovery es dinámico, no por imports estáticos). Lo valida `lint-imports`.
3. **Espeja la estructura por capas**: cada subsistema vive en `src/tequio/Core/<Subsistema>/`
   con un `__init__.py` que expone su API pública.
4. **Agrega tests** en `Tests/Core/...` (sin BD) y, si cambia comportamiento público,
   **documéntalo** en `documentation/`.

Para entender un subsistema antes de tocarlo, lee su página en
[documentation/](documentation/README.md).

## Tests

- Espeja `src/tequio/` en `Tests/` (misma ruta). Tests **unitarios y sin BD**: usa fakes y
  monkeypatch, no levantes Redis/Postgres.
- Corre uno solo: `uv run pytest Tests/Core/Cron/test_Schedule.py -x`.

## Checklist del PR

- [ ] `ruff format --check .` y `ruff check .` pasan
- [ ] `mypy` pasa (estricto)
- [ ] `lint-imports` pasa (no rompiste las fronteras)
- [ ] `pytest` pasa
- [ ] `uv build` construye sdist + wheel
- [ ] Subject en Conventional Commits
- [ ] Sin datos personales, secretos ni credenciales
- [ ] Si cambió comportamiento público, actualizaste `documentation/`

## Código de Conducta

Este proyecto adopta el [Código de Conducta](CODE_OF_CONDUCT.md) (Contributor Covenant
2.1). Al participar, aceptas cumplirlo.

## Licencia

Al contribuir aceptas que tu aporte queda bajo la [Licencia MIT](LICENSE).
