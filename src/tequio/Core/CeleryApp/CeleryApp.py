"""Celery central. Descubre tareas y crons de los módulos presentes."""

from __future__ import annotations

from typing import Any

from celery import Celery

from tequio.Core.Config import settings
from tequio.Core.Console import import_submodules
from tequio.Core.Logging import setup_logging
from tequio.Core.Registry import collect_beat_schedule, import_all_tasks

# Logging unificado (Loguru) también en worker/beat.
setup_logging()

celery_app = Celery(
    "app",  # nombre genérico (Core reutilizable); las tasks llevan su nombre explícito
    # Broker-agnostic: redis://, amqp:// (RabbitMQ), sqs://, ... Result backend OPCIONAL
    # (None por default; crons fire-and-forget).
    broker=settings.effective_broker_url,
    backend=settings.effective_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
    timezone=settings.timezone,
    enable_utc=True,
    worker_hijack_root_logger=False,  # el logging lo maneja Loguru
)

# visibility_timeout SOLO aplica a redis/SQS (RabbitMQ/AMQP lo ignora). Explícito para
# garantizar `lock_timeout > visibility_timeout` por construcción (ver Cron.py).
if settings.broker_uses_visibility_timeout:
    celery_app.conf.broker_transport_options = {"visibility_timeout": settings.redis_visibility_timeout}

# QUEUE_NAMESPACE: en un broker COMPARTIDO, mueve la cola por defecto de 'celery' a
# f"{ns}.celery" para que dos apps en el mismo redis db NO se roben las tasks SIN cola
# explícita (events.handle, Mail.queue sin cola, jobs/crons a la default). Las colas
# con nombre las prefija qualified_queue en cada call-site; ésta cubre el resto. Sin
# namespace NO se toca conf: la default 'celery' de Celery queda intacta (retrocompatible).
if settings.queue_namespace:
    celery_app.conf.task_default_queue = f"{settings.queue_namespace}.celery"


@celery_app.on_after_configure.connect
def _discover_modules(sender: Celery, **_: Any) -> None:
    """Discovery DIFERIDO (no en tiempo de import) para evitar el ciclo de imports
    Cron → CeleryApp → import_all_tasks() → command del módulo → Cron (a medio
    inicializar). Se ejecuta cuando Celery finaliza su configuración (arranque de
    worker/beat), con `app.Core.Cron` ya completamente cargado.

    Registra las tareas (Jobs + Console/Commands) y arma el `beat_schedule`. Ese
    schedule fusiona DOS fuentes (ver Registry.collect_beat_schedule): los
    `@cron_task` descubiertos (convertidos a crontab) MÁS los `beat_schedule`
    declarados en cada `Console/Kernel.py` (estos con precedencia). El orden importa:
    `import_all_tasks()` corre ANTES, así `registered_crons()` ya está poblado cuando
    se colecciona el schedule. Registrar tareas NO las dispara; el único disparo
    automático es `celery beat`, y cada cron respeta su guard
    `@cron_task(environments=[...])` AL EJECUTAR.
    """
    import_all_tasks()
    import_submodules("tequio.Core.Mail")  # tasks de correo del framework (mail.send) para el worker
    import_submodules("tequio.Core.Events")  # task events.handle: el worker corre observers encolados
    sender.conf.beat_schedule = collect_beat_schedule()
