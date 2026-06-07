"""Configuración central tipada (pydantic-settings). El .env es la ÚNICA fuente
de verdad de secretos/config por-entorno; infraestructura va SIN default
(obligatoria) para fallar claro si falta.
"""

from __future__ import annotations

import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default local para lo ENCOLADO (broker y lock) cuando no se configura nada. Es solo
# un FALLBACK de conveniencia para dev; no asumimos que siempre haya redis (los flujos
# síncronos no lo tocan). El config expone BROKER_URL/LOCK_URL (agnósticos), no un
# "REDIS_URL" redis-específico.
_DEFAULT_LOCAL_REDIS = "redis://localhost:6379/0"


def _host_timezone() -> str:
    """IANA timezone del HOST — el default cuando no se define TIMEZONE en .env.

    El framework NO impone zona horaria: es responsabilidad del dev/devops fijar
    TIMEZONE explícito (importante sobre todo si quien monta la app no es quien la
    programa — un server suele estar en UTC). Cae a 'UTC' si no se puede detectar.
    """
    try:
        import tzlocal

        return str(tzlocal.get_localzone_name() or "UTC")
    except Exception:
        return "UTC"


class Settings(BaseSettings):
    # extra="ignore": varios módulos comparten el mismo .env; cada Settings
    # ignora las variables que no declara.
    # env_file NO está clavado al CWD: se lee de TEQUIO_ENV_FILE (default ".env"). Así un
    # mismo despliegue puede apuntar a otro archivo (p. ej. TEQUIO_ENV_FILE=/run/secrets/app.env
    # en docker) SIN symlinkear .env al CWD del proceso (el hack que necesitaban los beats).
    model_config = SettingsConfigDict(
        env_file=os.environ.get("TEQUIO_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Infraestructura ---
    # Default sqlite local: tequio arranca y se usa SIN configurar nada (zero-config, como
    # Django en dev) → `tequio new`/`tequio serve` funcionan de inmediato. Siempre hay BD
    # (tequio la requiere); el default solo evita el crash de primer arranque. En QA/prod
    # pon tu motor real en .env: DATABASE_URL=postgresql+psycopg://... (o mysql+pymysql://...).
    database_url: str = "sqlite:///./tequio.db"

    # --- Colas / broker-agnostic ---
    # BROKER de Celery: CUALQUIER transporte (redis://, amqp:// RabbitMQ, sqs://, ...).
    # Vacío => redis local por default. Solo se usa para lo ENCOLADO (los flujos
    # síncronos no lo tocan). ActiveMQ NO es compatible (AMQP 1.0).
    broker_url: str = ""
    # Result backend: OPCIONAL. Nuestros crons son fire-and-forget, así que por default
    # NO hay backend (vacío). Ponlo solo si necesitas leer resultados (AsyncResult).
    result_backend_url: str = ""
    # Store de LOCKS para without_overlapping: redis da `.lock()`, los MQ no. Va aparte
    # del broker (un redis chico basta). Vacío => redis local por default.
    lock_url: str = ""

    # Visibility-timeout (segundos) — SOLO aplica a redis/SQS: si una task no se
    # reconoce en este tiempo, el broker la REENTREGA. El default lock de @cron_task se
    # deriva de aquí para garantizar `lock_timeout > visibility_timeout` por construcción.
    redis_visibility_timeout: int = 3600

    # --- Reintentos de tasks (defaults framework-wide; backoff exponencial con jitter) ---
    # Son los DEFAULTS de `retry_policy(...)` (app/Core/CeleryApp). Se pueden fijar por .env
    # O sobreescribir A MANO en código al declarar cada task. Solo afectan a tasks que OPTAN
    # por reintentar (pasan `autoretry_for`); NUNCA a los crons. 0 => sin reintentos.
    task_max_retries: int = 3
    task_retry_backoff: int = 2  # segundos base del 1er reintento (luego se duplica)
    task_retry_backoff_max: int = 600  # tope del backoff entre reintentos (10 min)

    # --- Operativo ---
    # Default GENÉRICO (Core es reutilizable): cada proyecto pone su APP_NAME en .env.
    app_name: str = "App"
    app_env: str = "qa"  # local | qa | production (como config('app.env') del legacy)
    # Locale de fallback de toda la app (i18n transversal: correos, API, etc.) cuando
    # no se pasa locale explícito. Override en .env con APP_FALLBACK_LOCALE.
    app_fallback_locale: str = "es"
    # Locale de Faker para factories/seeders (datos falsos). Configurable: "es_MX", "es_ES",
    # "en_US", … (cualquier locale de Faker). Lo usa tequio.Core.Database.Faker.
    faker_locale: str = "es_MX"
    # Default = zona del HOST (no la imponemos). El dev/devops DEBE fijar TIMEZONE en .env.
    timezone: str = Field(default_factory=_host_timezone)

    # --- Correo (equivalente a config('mail.*') del legacy) ---
    # En local apuntan a Mailpit (localhost:1025); en QA/prod al SMTP corporativo.
    # MAIL_DRIVER (= mail.default de Laravel): cómo se MANDA.
    #   "smtp" (default) -> envía por SMTP real.
    #   "log"            -> NO envía: escribe el correo en el log (dev/sin SMTP; cross-platform).
    #   "null"/"array"   -> no-op: descarta el correo (tests / silenciar).
    mail_driver: str = "smtp"
    mail_host: str = "localhost"
    mail_port: int = 1025
    mail_username: str = ""
    mail_password: str = ""
    mail_encryption: str = ""  # "" (sin cifrado, ej. Mailpit) | "tls" (STARTTLS) | "ssl" (SMTPS)
    # Remitente. Aceptamos el nombre de Laravel (MAIL_FROM_ADDRESS) y el natural.
    mail_from_email: str = Field(
        default="no-reply@example.com",
        validation_alias=AliasChoices("MAIL_FROM_ADDRESS", "MAIL_FROM_EMAIL"),
    )
    mail_from_name: str = "App"

    # --- Events ---
    # Igual para los Observers: un observer que falla se loguea ruidoso (best-effort). Con esto
    # en True (dev/test), RE-LANZA — para que el bug del observer truene fuerte. Default False.
    events_strict: bool = False

    # --- Logging (Loguru) ---
    log_level: str = "INFO"
    log_json: bool = False
    log_dir: str = "logs"

    # --- Layout del PROYECTO: DÓNDE vive el código del USUARIO ---
    # tequio instalado como paquete NO puede adivinar dónde está tu proyecto contando
    # carpetas desde sí mismo (en site-packages eso apunta a otro lado). Lo lee de aquí.
    # Los DEFAULTS = el layout de ESTE repo, así no se rompe nada si no configuras.
    # Un proyecto EXTERNO los apunta a su propio paquete/carpetas vía .env:
    #   MODULES_PACKAGE=app.Modules   MODELS_PACKAGE=app.Models
    #   USER_VIEWS_DIR=app/Resources/Views   MIGRATIONS_DIR=migrations  ...
    # Paquetes (notación punteada, importables):
    modules_package: str = "tequio.Modules"  # dónde escanear los módulos (rutas/jobs/crons/seeders/i18n/vistas)
    models_package: str = "tequio.Models"  # dónde viven los modelos (se cargan en Base.metadata)
    app_commands_package: str = "tequio.Console.Commands"  # commands GENERALES del proyecto (opcional; tolera ausencia)
    # Carpetas de recursos del USUARIO (relativas al cwd del proyecto). "" => no se usan
    # (en ESTE repo van vacías: las vistas/lang del framework salen del paquete).
    user_views_dir: str = ""  # p. ej. "app/Resources/Views" en un proyecto externo
    user_lang_dir: str = ""  # p. ej. "app/Resources/Lang"
    # Carpeta de migraciones Alembic, relativa al cwd del proyecto. Default "migrations".
    migrations_dir: str = "migrations"

    # Raíz del código del USUARIO donde escribe `make:*` (modelos/controllers/módulos),
    # relativa al cwd. Default "app" (el layout que genera `tequio new`). En el repo del
    # PROPIO framework, donde el código vive en src/tequio, pon APP_DIR=src/tequio en .env.
    app_dir: str = "app"

    @property
    def effective_broker_url(self) -> str:
        """Broker de Celery; cae al redis local por default si BROKER_URL está vacío."""
        return self.broker_url or _DEFAULT_LOCAL_REDIS

    @property
    def effective_lock_url(self) -> str:
        """Store de locks (redis); cae al redis local por default si LOCK_URL está vacío."""
        return self.lock_url or _DEFAULT_LOCAL_REDIS

    @property
    def effective_result_backend(self) -> str | None:
        """Result backend; None (sin backend) por default — crons fire-and-forget."""
        return self.result_backend_url or None

    @property
    def broker_uses_visibility_timeout(self) -> bool:
        """visibility_timeout solo aplica a redis/SQS (no a RabbitMQ/AMQP, etc.)."""
        return self.effective_broker_url.startswith(("redis://", "rediss://", "sqs://"))


settings = Settings()
