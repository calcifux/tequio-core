"""Política de reintentos reutilizable para tasks de Celery (backoff exponencial).

Centraliza el cableado de `autoretry_for` + backoff para no repetirlo en cada task y,
sobre todo, para que sea configurable de DOS formas (no solo por `.env`):

  - por **`.env`**: defaults framework-wide (`TASK_MAX_RETRIES`, `TASK_RETRY_BACKOFF`,
    `TASK_RETRY_BACKOFF_MAX`), y
  - **A MANO en código**: pasando los argumentos explícitos al declarar la task, que
    pisan el default por-task sin tocar el entorno.

Uso:

    from tequio.Core.CeleryApp import celery_app, retry_policy

    # Toma los defaults de .env:
    @celery_app.task(bind=True, name="mail.send", **retry_policy(retry_for=(SMTPException,)))
    def send_mail_task(self, ...): ...

    # O configurado A MANO (pisa el .env para ESTA task):
    @celery_app.task(bind=True, name="sync.invoices",
                     **retry_policy(retry_for=(ConnectionError,), max_retries=5, backoff=10))
    def sync_invoices(self, ...): ...

Reglas:
  - `retry_for` SOLO debe listar excepciones TRANSITORIAS (timeouts, desconexiones, fallos
    de red). Las permanentes (validación, auth, archivo inexistente) NO deben reintentarse:
    reintentar no las arregla y agota intentos.
  - NO apliques esto a crons (`@cron_task`): un cron se reagenda solo y ya trae lock
    anti-overlapping; un reintento encima duplicaría trabajo.
"""

from __future__ import annotations

from typing import Any

from tequio.Core.Config import settings


def retry_policy(
    *,
    retry_for: tuple[type[BaseException], ...],
    max_retries: int | None = None,
    backoff: int | bool | None = None,
    backoff_max: int | None = None,
    jitter: bool = True,
) -> dict[str, Any]:
    """Construye los kwargs de reintento para `@celery_app.task(**retry_policy(...))`.

    Cada parámetro en `None` toma su default de `Settings` (`.env`); pásalo explícito
    para fijarlo A MANO en esta task. `retry_for` es obligatorio: declara qué excepciones
    son transitorias (las únicas que se reintentan).

    Args:
        retry_for: excepciones TRANSITORIAS que disparan reintento (`autoretry_for`).
        max_retries: nº máximo de reintentos. None => `settings.task_max_retries`.
        backoff: segundos base del backoff exponencial (o False para desactivarlo).
                 None => `settings.task_retry_backoff`.
        backoff_max: tope del backoff entre reintentos. None => `settings.task_retry_backoff_max`.
        jitter: añade aleatoriedad al backoff para evitar reintentos sincronizados.
    """
    return {
        "autoretry_for": retry_for,
        "max_retries": settings.task_max_retries if max_retries is None else max_retries,
        "retry_backoff": settings.task_retry_backoff if backoff is None else backoff,
        "retry_backoff_max": settings.task_retry_backoff_max if backoff_max is None else backoff_max,
        "retry_jitter": jitter,
    }
