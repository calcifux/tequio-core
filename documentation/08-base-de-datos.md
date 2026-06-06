# Base de datos: configuración del motor

La capa de datos de tequio es **agnóstica del motor SQL**. Eliges la base con
`DATABASE_URL` y el resto del código no cambia. Detrás está SQLAlchemy 2.0, con todo lo
específico de cada dialecto **aislado** en `tequio/Core/Database/Session.py`.

tequio es worker-side: la BD la consultan jobs, crons, observers, handlers y seeders —
no hay capa HTTP. (La parte web de milpa —rutas, JSON, DTOs sobre la API— vive en
[milpa](https://github.com/calcifux/milpa); aquí la misma capa de datos alimenta procesos en
segundo plano.)

## SQLite por default: arranca sin configurar nada

A diferencia de milpa (donde `DATABASE_URL` es obligatoria), tequio trae un **default
local de SQLite** para que un servicio chico corra de inmediato (zero-config):

```python
database_url: str = "sqlite:///./tequio.db"
```

Así `tequio new` y los comandos arrancan sin tocar el `.env`. **Siempre hay BD** (tequio
la requiere); el default solo evita el crash del primer arranque. En QA/producción pon tu
motor real en `.env`. Ver [Configuración](03-configuracion.md).

## Elegir el motor: `DATABASE_URL`

El prefijo de la URL determina el dialecto (y el driver):

```
sqlite:///./tequio.db                           # SQLite (default, va GRATIS: stdlib)
mysql+pymysql://user:pass@host:3306/db          # MySQL / MariaDB  (uv sync --extra mysql)
postgresql+psycopg://user:pass@host:5432/db     # PostgreSQL       (uv sync --extra postgres)
oracle+oracledb://user:pass@host:1521/?service_name=db   # Oracle  (--extra oracle)
mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+18   # SQL Server (--extra mssql)
```

tequio detecta el backend automáticamente (`make_url(...).get_backend_name()`). No hay
nada hardcodeado: cambiar de motor es cambiar la URL (y, si aplica, instalar su driver).

### SQLite va gratis; los demás motores son extras

SQLite es la stdlib de Python: el default no requiere instalar nada. Cada motor
cliente-servidor instala **solo su** driver, como extra opcional:

| Motor | Extra | Driver |
|-------|-------|--------|
| SQLite | (ninguno) | `sqlite3` (stdlib) |
| MySQL / MariaDB | `mysql` | `pymysql` |
| PostgreSQL | `postgres` | `psycopg` v3 (binario) |
| Oracle | `oracle` | `oracledb` |
| SQL Server | `mssql` | `pyodbc` (requiere el ODBC Driver del SO) |

```bash
uv sync --extra postgres                 # en el repo / con uv
pip install "tequio-core[postgres]"      # con pip (tequio-core AÚN NO está en PyPI)
```

!!! note "tequio-core todavía no se publica en PyPI"
    El nombre del paquete será `tequio-core` (import `tequio`), pero a la fecha **no está
    publicado**. Mientras tanto se usa desde el repo con `uv sync`.

Ver [Instalación](02-instalacion.md) para el detalle de cada extra.

## El engine y el pool

`Session.py` construye el `engine` con kwargs que difieren **por motor**:

- **SQLite**: `check_same_thread=False` (la conexión cruza hilos: el worker de Celery es
  multi-hilo); si es en memoria (`:memory:`), `StaticPool` (una sola conexión compartida,
  útil en tests).
- **Cliente-servidor** (MySQL/PostgreSQL/Oracle/MSSQL): `pool_pre_ping=True` (verifica la
  conexión antes de usarla) y `pool_recycle=3600` (recicla cada hora). Esto importa
  especialmente en tequio: los workers son **procesos longevos** y los servidores cierran
  conexiones inactivas.

## Zona horaria por conexión

Cada vez que se abre una conexión, tequio fija su zona horaria a la de la app
(`TIMEZONE`), vía un event hook `connect`. Así `NOW()` / `func.now()` (los timestamps
automáticos) salen en hora local **sin** que Python intervenga. La sentencia depende del
motor:

| Motor | Sentencia | Nota |
|-------|-----------|------|
| MySQL/MariaDB | `SET time_zone = '-06:00'` | offset (los nombres IANA exigen cargar tz tables) |
| PostgreSQL | `SET TIME ZONE 'America/Mexico_City'` | nombre IANA (Postgres trae las zonas) |
| Oracle | `ALTER SESSION SET TIME_ZONE = '-06:00'` | offset vía ALTER SESSION |
| SQLite / SQL Server | (sin zona por sesión) | en SQLite los timestamps caen a UTC; afecta solo dev/tests |

Por eso conviene **fijar `TIMEZONE`** explícito en el `.env` de un servidor (suele estar
en UTC) — más aún en tequio, donde un cron que corre "a las 8:00" depende de qué zona es
esa. Si no defines `TIMEZONE`, el default es la zona del **host**. Ver
[Configuración](03-configuracion.md).

## `SessionLocal`

```python
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

`autocommit=False` (el commit es explícito, lo gobierna `@transactional`/`session_scope`)
y `autoflush=False` (flush explícito, más predecible). No la usas directo: la capa
transaccional la envuelve (ver [Repositorios y transacciones](10-repositorios-y-transacciones.md)).

## ¿Crear tablas?

tequio **no crea el esquema solo**: no existe un `AUTO_CREATE_TABLES` ni un
`create_all()` al arrancar (a diferencia de algunas versiones web). El esquema se versiona
**siempre** con migraciones (Alembic). Los modelos se descubren solos para poblar
`Base.metadata` (lo necesita el autogenerate), pero eso **no** toca la BD — solo registra
las tablas en memoria. Ver [Modelos](09-modelos.md).

## Migraciones (Alembic)

Para una BD **propia** (greenfield), gestiona el esquema con migraciones versionadas.
tequio trae Alembic integrado y operado por `jornal` (estilo `php artisan migrate`).
La invocación es por **grupo** (`migrate <command>`):

```bash
python jornal migrate make -m "crear tabla facturas"  # genera la revisión (autogenerate)
python jornal migrate run                              # aplica las pendientes (upgrade head)
python jornal migrate status                           # revisión actual + historial
python jornal migrate rollback                         # revierte una (downgrade -1)
```

Cada subcomando acepta opciones:

| Comando | Opción | Efecto |
|---------|--------|--------|
| `migrate make` | `-m/--message` (obligatoria) | descripción corta de la revisión |
| `migrate make` | `--autogenerate` / `--empty` | detectar cambios de los modelos, o crear una revisión vacía |
| `migrate run` | `--to` (default `head`) | revisión objetivo |
| `migrate rollback` | `--to` (default `-1`) | revisión objetivo |

Cómo encaja con el resto del framework (sin duplicar config):

- **Una sola fuente de conexión.** No hay `alembic.ini`: la config se arma en código
  (`tequio/Core/Database/Migrations.py`) y `migrations/env.py` toma la BD de `DATABASE_URL`
  (Settings) reusando el **engine** del framework. Cambias de motor sin tocar Alembic.
- **Autogenerate desde tus modelos.** `env.py` llama a `import_all_models()` (el mismo
  discovery de la app) para poblar `Base.metadata`; el `make` compara esos modelos contra
  el esquema real. La `naming_convention` de `Base` hace los nombres de
  índices/constraints reproducibles. `compare_type=True` detecta también cambios de TIPO
  de columna.
- **Revisa antes de aplicar.** El archivo cae en `migrations/versions/` (versionado en
  git); `migrate make` **no** toca la BD — solo `migrate run` aplica.
- **BD legacy:** no generes migraciones de tablas que no administras. Úsalo solo para las
  tablas NUEVAS del proyecto.

### Catálogos fijos: siémbralos en la migración (`op.bulk_insert`)

Para datos **de catálogo** que son parte del esquema (estados, tipos, roles fijos: cambian
con el código, no con el uso), no necesitas un seeder aparte — siémbralos **dentro de la
propia migración** con `op.bulk_insert`. Así el catálogo viaja versionado con el
`upgrade`/`downgrade` y queda igual en todos los entornos:

```python
def upgrade() -> None:
    estatus = op.create_table(
        "estatus_factura",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("clave", sa.String(20), nullable=False, unique=True),
        sa.Column("etiqueta", sa.String(60), nullable=False),
    )
    op.bulk_insert(  # el catálogo es parte del esquema → va aquí, no en un seeder
        estatus,
        [
            {"id": 1, "clave": "borrador", "etiqueta": "Borrador"},
            {"id": 2, "clave": "timbrada", "etiqueta": "Timbrada"},
            {"id": 3, "clave": "cancelada", "etiqueta": "Cancelada"},
        ],
    )


def downgrade() -> None:
    op.drop_table("estatus_factura")
```

Regla práctica: **catálogo fijo → migración** (`op.bulk_insert`); **datos de ejemplo /
demo o volumen variable → seeder + factory** (`db seed`, Faker). Ver
[La consola jornal](07-consola-jornal.md).

## `db fresh` y `db seed`: recrear y poblar

Dos atajos de desarrollo del grupo `db` (= `php artisan migrate:fresh --seed` y
`db:seed`):

```bash
python jornal db fresh    # DESTRUCTIVO: downgrade a base → upgrade head → corre seeders
python jornal db seed     # solo corre los seeders (puebla la BD)
```

- `db fresh` **borra todos los datos** (baja todo a `base`, re-migra a `head` y siembra).
  Pide confirmación; pásale `--force` en CI/scripts.
- `db seed` descubre las subclases de `Seeder` de cada módulo y las ejecuta, cada una en
  su propia transacción. En el Demo, `DemoSeeder` siembra notas con `NoteFactory` (Faker)
  más una a mano — ver [Modelos](09-modelos.md) y
  [Repositorios y transacciones](10-repositorios-y-transacciones.md).

## ¿Y NoSQL?

Hoy la capa cubre **SQL**. NoSQL (Mongo, etc.) está **diferido on-demand**: cuando se
necesite, se implementa detrás del mismo patrón `Repository`. No hay un adapter NoSQL
especulativo.

## Siguiente paso

[Modelos](09-modelos.md).
