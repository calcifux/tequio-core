# Instalación

## Requisitos

- **Python 3.14+**.
- Una **base de datos** alcanzable. El engine es agnóstico del motor (SQLite,
  MySQL/MariaDB, PostgreSQL, Oracle, SQL Server); se elige con `DATABASE_URL`. SQLite
  viene en la stdlib: tequio arranca **sin configurar nada** (default `sqlite:///./tequio.db`).
- **Redis** (o cualquier broker de Celery) **solo si** usas `@job` / `@cron_task` en
  background. Los flujos síncronos no lo tocan. En local, un `docker compose up -d`
  levanta Redis.
- (Recomendado) [**uv**](https://docs.astral.sh/uv/) como gestor de entorno y deps.

!!! note "tequio NO trae capa web"
    No hay servidor HTTP ni Node/Vite que instalar — eso vive en
    [milpa](https://github.com/calcifux/milpa). tequio es puro worker-side. **Sí** trae
    correo: el `docker-compose.yml` incluye **Mailpit** (opcional) para ver los correos en
    una UI durante el desarrollo; ver [Correo](20-correo.md).

## Instalar el paquete

El paquete se publica en PyPI como **`tequio-core`** (el import y el comando siguen siendo
`tequio`).

### Con `pip`

```bash
pip install tequio-core            # sqlite (stdlib), sin drivers extra
```

### Con `uv` (recomendado en el repo del propio framework)

```bash
uv sync                            # crea el entorno y resuelve deps desde pyproject.toml / uv.lock
```

Para correr cualquier comando, antepón `uv run` (no necesitas activar el venv):

```bash
uv run python jornal list
uv run pytest
```

## Drivers de base de datos

El core es **agnóstico del motor**. SQLite va **gratis** (stdlib); para otros motores
instala el extra del tuyo:

```bash
uv sync --extra mysql         # MySQL / MariaDB (pymysql)
uv sync --extra postgres      # PostgreSQL (psycopg v3)
uv sync --extra oracle        # Oracle (oracledb)
uv sync --extra mssql         # SQL Server (pyodbc; requiere el ODBC Driver del SO)
```

Con pip: `pip install "tequio-core[postgres]"`.

El motor se elige con el prefijo de `DATABASE_URL` (ver [Base de datos](08-base-de-datos.md)):

```
sqlite:///./tequio.db          mysql+pymysql://...           postgresql+psycopg://...
oracle+oracledb://...          mssql+pyodbc://...
```

## Crear un proyecto: `tequio new`

El scaffolder genera un proyecto **listo para correr** (con `app/`, `jornal`, `.env` y
`migrations/`, y la config apuntando a TU código):

```bash
tequio new mi-servicio              # proyecto mínimo (módulo Hello de ejemplo)
tequio new mi-servicio --demo       # + módulo Demo completo (referencia viva)
```

Con `--demo` copia además el módulo **Demo**, un sistema de notas worker-side que ejercita
todo: jobs/crons → log, eventos/observers, Mediator, Pipeline, y un seeder con Faker.

Siguientes pasos que imprime `tequio new`:

```bash
cd mi-servicio
uv sync                                            # instala tequio + dependencias
python jornal migrate run                          # aplica las migraciones (--demo ya trae la suya)
python jornal db seed                              # (solo --demo) puebla notas (DemoSeeder)
python jornal queue work                           # arranca el worker (procesa los @job)
```

## Configuración mínima

`tequio new` deja un `.env` listo (copia del `.env.example`) para que arranque sin pasos
extra. Si instalaste el paquete a mano, copia el ejemplo:

```bash
cp .env.example .env
```

SQLite es el default, así que un clone limpio **arranca sin configurar nada**. En QA/prod
fija tu motor real con `DATABASE_URL`. Ver [Configuración](03-configuracion.md).

## Levantar la infraestructura (opcional)

Docker solo corre infraestructura de desarrollo (Redis y Mailpit). La app corre en el host.
Lo necesitas si vas a despachar jobs/crons en background (Redis) o quieres ver los correos en
una UI (Mailpit; ver [Correo](20-correo.md)):

```bash
docker compose up -d        # Redis (6379) + Mailpit (SMTP 1025 · UI 8025)
```

## Verificar la instalación

```bash
python jornal list                 # debe listar los comandos
uv run pytest                      # la suite debe pasar (sin BD)
python jornal queue work           # arranca el worker de Celery (requiere broker)
```

## Siguiente paso

[Configuración](03-configuracion.md).
