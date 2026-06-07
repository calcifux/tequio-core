"""Fachada pública de tequio: la API estable en UN import plano.

    from tequio import job, cron_task, celery_app, Mailable, Repository, ...

Re-exporta la superficie que el README, el Demo y el skeleton enseñan; las rutas
profundas (`from tequio.Core.Jobs import job`) SIGUEN siendo válidas y estables.

PEREZOSA a propósito (PEP 562, `__getattr__` de módulo): `import tequio` a secas NO
tiene efectos colaterales. Una fachada eager arrastraría `Core.CeleryApp.CeleryApp`,
que instancia Celery + lee Settings + configura logging EN IMPORT TIME — eso debe
ocurrir cuando pides `tequio.celery_app`, no cuando una herramienta (mkdocs, pickle,
el smoke del CI) hace `import tequio`. Mismo espíritu que el Faker perezoso de
`Core/Database/Faker.py`. El bloque TYPE_CHECKING da los tipos reales a mypy/IDEs
(el paquete publica `py.typed`, PEP 561).
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from tequio.Core.CeleryApp import QueueUnavailableError, broker_guard, celery_app, retry_policy
    from tequio.Core.Clock import Clock, FixedClock, SystemClock
    from tequio.Core.Config import Settings, settings
    from tequio.Core.Console import console_command
    from tequio.Core.Cron import (
        cron,
        cron_task,
        daily,
        daily_at,
        every_fifteen_minutes,
        every_five_minutes,
        every_minute,
        every_minutes,
        every_ten_minutes,
        every_thirty_minutes,
        hourly,
        hourly_at,
        monthly,
        weekly,
    )
    from tequio.Core.Database import (
        Base,
        CursorPage,
        Factory,
        Page,
        Repository,
        SoftDeleteMixin,
        TimestampMixin,
        current_session,
        session_scope,
        transactional,
    )
    from tequio.Core.Database.Faker import faker
    from tequio.Core.Database.Seeder import Seeder
    from tequio.Core.Errors import ConflictError, DomainError, ResourceNotFoundError
    from tequio.Core.Events import Observer, dispatch
    from tequio.Core.Jobs import Job, job
    from tequio.Core.Mail import Mail, Mailable, MailContent
    from tequio.Core.Mediator import handles, send
    from tequio.Core.Pipeline import Pipe, Pipeline

# Dónde vive CADA símbolo (su módulo canónico). `broker_guard`/`retry_policy` apuntan a
# sus módulos definidores (Dispatch/Retry), NO al paquete CeleryApp: pedirlos no debe
# instanciar Celery (solo `celery_app` paga ese costo, porque eso es lo que pides).
_EXPORTS: Final[dict[str, str]] = {
    # Celery: la app, la guarda de broker y la política de reintentos
    "celery_app": "tequio.Core.CeleryApp",
    "broker_guard": "tequio.Core.CeleryApp.Dispatch",
    "QueueUnavailableError": "tequio.Core.CeleryApp.Dispatch",
    "retry_policy": "tequio.Core.CeleryApp.Retry",
    # Jobs on-demand (`@job` + `.dispatch()`)
    "Job": "tequio.Core.Jobs",
    "job": "tequio.Core.Jobs",
    # Crons (`@cron_task`) + azúcar de schedule (daily/hourly/…)
    "cron": "tequio.Core.Cron",
    "cron_task": "tequio.Core.Cron",
    "daily": "tequio.Core.Cron",
    "daily_at": "tequio.Core.Cron",
    "every_fifteen_minutes": "tequio.Core.Cron",
    "every_five_minutes": "tequio.Core.Cron",
    "every_minute": "tequio.Core.Cron",
    "every_minutes": "tequio.Core.Cron",
    "every_ten_minutes": "tequio.Core.Cron",
    "every_thirty_minutes": "tequio.Core.Cron",
    "hourly": "tequio.Core.Cron",
    "hourly_at": "tequio.Core.Cron",
    "monthly": "tequio.Core.Cron",
    "weekly": "tequio.Core.Cron",
    # Correo (Mailables + envío síncrono/encolado)
    "Mail": "tequio.Core.Mail",
    "Mailable": "tequio.Core.Mail",
    "MailContent": "tequio.Core.Mail",
    # Eventos + observers
    "Observer": "tequio.Core.Events",
    "dispatch": "tequio.Core.Events",
    # Mediator (commands/queries con handler único)
    "handles": "tequio.Core.Mediator",
    "send": "tequio.Core.Mediator",
    # Pipeline (cadena de pipes)
    "Pipe": "tequio.Core.Pipeline",
    "Pipeline": "tequio.Core.Pipeline",
    # Base de datos: declarativa, repositorios, sesiones y transacciones
    "Base": "tequio.Core.Database",
    "CursorPage": "tequio.Core.Database",
    "Factory": "tequio.Core.Database",
    "Page": "tequio.Core.Database",
    "Repository": "tequio.Core.Database",
    "SoftDeleteMixin": "tequio.Core.Database",
    "TimestampMixin": "tequio.Core.Database",
    "current_session": "tequio.Core.Database",
    "session_scope": "tequio.Core.Database",
    "transactional": "tequio.Core.Database",
    "Seeder": "tequio.Core.Database.Seeder",
    "faker": "tequio.Core.Database.Faker",
    # Consola (commands estilo artisan)
    "console_command": "tequio.Core.Console",
    # Configuración (pydantic-settings)
    "Settings": "tequio.Core.Config",
    "settings": "tequio.Core.Config",
    # Reloj inyectable (= java.time.Clock / Carbon::setTestNow)
    "Clock": "tequio.Core.Clock",
    "FixedClock": "tequio.Core.Clock",
    "SystemClock": "tequio.Core.Clock",
    # Errores de dominio (RFC 9457-ready)
    "ConflictError": "tequio.Core.Errors",
    "DomainError": "tequio.Core.Errors",
    "ResourceNotFoundError": "tequio.Core.Errors",
}

# Lista ESTÁTICA a propósito (no `sorted(_EXPORTS)`): mypy y ruff solo entienden
# re-exports con un `__all__` literal. El test de la fachada la mantiene en sync.
__all__ = [
    "Base",
    "Clock",
    "ConflictError",
    "CursorPage",
    "DomainError",
    "Factory",
    "FixedClock",
    "Job",
    "Mail",
    "MailContent",
    "Mailable",
    "Observer",
    "Page",
    "Pipe",
    "Pipeline",
    "QueueUnavailableError",
    "Repository",
    "ResourceNotFoundError",
    "Seeder",
    "Settings",
    "SoftDeleteMixin",
    "SystemClock",
    "TimestampMixin",
    "broker_guard",
    "celery_app",
    "console_command",
    "cron",
    "cron_task",
    "current_session",
    "daily",
    "daily_at",
    "dispatch",
    "every_fifteen_minutes",
    "every_five_minutes",
    "every_minute",
    "every_minutes",
    "every_ten_minutes",
    "every_thirty_minutes",
    "faker",
    "handles",
    "hourly",
    "hourly_at",
    "job",
    "monthly",
    "retry_policy",
    "send",
    "session_scope",
    "settings",
    "transactional",
    "weekly",
]


def __getattr__(name: str) -> Any:
    """Resuelve los símbolos de `_EXPORTS` al primer acceso (PEP 562) y los cachea."""
    try:
        module_path = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module_path), name)
    globals()[name] = value  # cachea: los accesos siguientes ya no pasan por aquí
    return value


def __dir__() -> list[str]:
    """`dir(tequio)` lista la fachada completa aunque aún no se haya resuelto nada."""
    return sorted(set(globals()) | set(_EXPORTS))
