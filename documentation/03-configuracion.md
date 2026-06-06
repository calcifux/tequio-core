# Configuración

Toda la configuración vive en un archivo `.env` en la raíz y se lee a través de una
única clase `Settings` (pydantic-settings).

```bash
cp .env.example .env
```

## La clase `Settings`

`tequio/Core/Config/Settings.py` define la clase `Settings` (pydantic `BaseSettings`) y
exporta una **instancia única**:

```python
from tequio.Core.Config import settings

print(settings.app_name)
print(settings.database_url)
```

Se carga del `.env` **una sola vez** al arrancar el proceso (es un singleton). Cambiar el
`.env` requiere reiniciar. El atributo `extra="ignore"` permite que varios módulos
compartan el mismo `.env` sin chocar.

!!! tip "Zero-config en dev"
    A diferencia de milpa, `DATABASE_URL` **tiene default** (`sqlite:///./tequio.db`): un
    clone limpio arranca sin tocar nada. En QA/prod pon tu motor real en `.env`.

## Referencia de variables

Estas son las variables que tequio lee del `.env`. Las de **correo** tienen su propia
tabla abajo y se detallan en [Correo](20-correo.md).

### Base de datos

| Variable | Default | Para qué |
|----------|---------|----------|
| `DATABASE_URL` | `sqlite:///./tequio.db` | Conexión SQLAlchemy; el prefijo elige el motor. |

### Aplicación

| Variable | Default | Para qué |
|----------|---------|----------|
| `APP_NAME` | `App` | Nombre del proyecto (aparece en la ayuda del CLI). |
| `APP_ENV` | `qa` | Entorno: `local`, `qa`, `production`. Gatea crons (`environments`) y el `diagnose` del log. |
| `FAKER_LOCALE` | `es_MX` | Locale de Faker para factories/seeders (`es_MX`, `es_ES`, `en_US`, …). |
| `APP_FALLBACK_LOCALE` | `es` | Locale de respaldo de `t()` cuando no se pasa uno explícito (i18n de correos). Ver [Correo](20-correo.md). |
| `TIMEZONE` | zona del host | Zona IANA (ej. `America/Mexico_City`). Gobierna el reloj de crons y timestamps. |

!!! warning "`TIMEZONE`"
    Si se omite, tequio detecta la zona del **host**. En un servidor (suele estar en UTC)
    **fíjala explícita**: quien monta el server puede no ser quien programa.

### Colas / broker (Celery)

| Variable | Default | Para qué |
|----------|---------|----------|
| `BROKER_URL` | `""` → redis local | Transporte de Celery (`redis://…`, `amqp://…` RabbitMQ, `sqs://…`). |
| `RESULT_BACKEND_URL` | `""` → sin backend | Backend de resultados (opcional; crons son fire-and-forget). |
| `LOCK_URL` | `""` → redis local | Store de locks (redis) para `without_overlapping`. |
| `REDIS_VISIBILITY_TIMEOUT` | `3600` | Segundos antes de re-entregar una task (solo redis/SQS). |

Ver [Colas y tareas](13-colas-y-tareas.md).

### Reintentos de tasks

Defaults framework-wide de `retry_policy(...)`. Se pueden pisar **a mano** en código por
task. Solo afectan a tasks que **optan** por reintentar (pasan `retry_for`); nunca a los
crons.

| Variable | Default | Para qué |
|----------|---------|----------|
| `TASK_MAX_RETRIES` | `3` | Nº máximo de reintentos. `0` = sin reintentos. |
| `TASK_RETRY_BACKOFF` | `2` | Segundos base del 1er reintento (luego se duplica). |
| `TASK_RETRY_BACKOFF_MAX` | `600` | Tope del backoff entre reintentos (10 min). |

Ver [Jobs](12-jobs.md).

### Eventos

| Variable | Default | Para qué |
|----------|---------|----------|
| `EVENTS_STRICT` | `false` | `true` (dev/test) re-lanza el error de un Observer que falla, en vez de solo loguearlo. |

Ver [Eventos y Observers](15-eventos-y-observers.md).

### Logging (Loguru)

| Variable | Default | Para qué |
|----------|---------|----------|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LOG_JSON` | `false` | `true` agrega `logs/app.jsonl` (JSON Lines para Loki/Grafana). |
| `LOG_DIR` | `logs` | Directorio de logs. |

Ver [Logging](18-logging.md).

### Correo

Cómo se mandan los correos (worker-side). El detalle de cada driver y el flujo Mailable
están en [Correo](20-correo.md).

| Variable | Default | Para qué |
|----------|---------|----------|
| `MAIL_DRIVER` | `smtp` | Cómo se manda: `smtp` (real), `log` (al log, dev sin SMTP), `null`/`array` (no-op). |
| `MAIL_HOST` | `localhost` | Host SMTP. El default apunta a **Mailpit**. |
| `MAIL_PORT` | `1025` | Puerto SMTP (1025 = Mailpit). |
| `MAIL_USERNAME` | `""` | Usuario SMTP (vacío en Mailpit). |
| `MAIL_PASSWORD` | `""` | Contraseña SMTP (vacía en Mailpit). |
| `MAIL_ENCRYPTION` | `""` | `""` (sin cifrado, ej. Mailpit), `tls` (STARTTLS) o `ssl` (SMTPS). |
| `MAIL_FROM_ADDRESS` | `no-reply@example.com` | Remitente por defecto (alias: `MAIL_FROM_EMAIL`). |
| `MAIL_FROM_NAME` | `App` | Nombre del remitente por defecto. |

!!! warning "El default es `smtp`, no `log`"
    Sin configurar nada, `MAIL_DRIVER=smtp` apunta a Mailpit (`localhost:1025`). Si no tienes
    Mailpit (ni otro SMTP) arriba, el envío falla. Para dev sin SMTP, pon `MAIL_DRIVER=log`.

Ver [Correo](20-correo.md).

### Layout del proyecto

tequio instalado como paquete no puede adivinar dónde vive tu código contando carpetas
desde sí mismo (en `site-packages` eso apunta a otro lado): lo lee de estas variables. Un
proyecto generado con `tequio new` ya las trae apuntando a `app/`.

| Variable | Default | Para qué |
|----------|---------|----------|
| `MODULES_PACKAGE` | `tequio.Modules` | Paquete (punteado) donde se escanean los módulos (jobs/crons/seeders/observers…). |
| `MODELS_PACKAGE` | `tequio.Models` | Paquete donde viven los modelos (se cargan en `Base.metadata`). |
| `APP_COMMANDS_PACKAGE` | `tequio.Console.Commands` | Commands generales del proyecto (opcional; tolera ausencia). |
| `MIGRATIONS_DIR` | `migrations` | Carpeta de migraciones Alembic, relativa al cwd. |
| `APP_DIR` | `app` | Raíz donde `make:*` escribe (modelos/jobs/…), relativa al cwd. |
| `USER_VIEWS_DIR` | `""` | Vistas/plantillas propias de un proyecto externo (ej. `app/Resources/Views`). Vacío = usa las del paquete. |
| `USER_LANG_DIR` | `""` | Catálogos i18n propios de un proyecto externo (ej. `app/Resources/Lang`). Vacío = usa los del paquete. |

!!! note "En un proyecto creado con `tequio new`"
    El `.env` generado ya trae `MODULES_PACKAGE=app.Modules`, `MODELS_PACKAGE=app.Models`,
    `APP_COMMANDS_PACKAGE=app.Console.Commands`, `APP_DIR=app` y `MIGRATIONS_DIR=migrations`.
    No tocas nada salvo que muevas las carpetas.

## Propiedades calculadas útiles

`Settings` expone helpers para no repetir lógica de fallback:

| Propiedad | Qué devuelve |
|-----------|--------------|
| `settings.effective_broker_url` | `broker_url` o redis local si está vacío. |
| `settings.effective_lock_url` | `lock_url` o redis local si está vacío. |
| `settings.effective_result_backend` | `result_backend_url` o `None`. |
| `settings.broker_uses_visibility_timeout` | `True` si el broker es redis/SQS (no RabbitMQ). |

## Siguiente paso

[Estructura de directorios](04-estructura-directorios.md).
