"""Punto de entrada de Celery (paquete). Re-exporta el `celery_app` para que
los consumidores sigan importando con `from tequio.Core.CeleryApp import celery_app`.
"""

from __future__ import annotations

from tequio.Core.CeleryApp.CeleryApp import celery_app
from tequio.Core.CeleryApp.Dispatch import QueueUnavailableError, broker_guard, qualified_queue
from tequio.Core.CeleryApp.Retry import retry_policy

__all__ = ["QueueUnavailableError", "broker_guard", "celery_app", "qualified_queue", "retry_policy"]
