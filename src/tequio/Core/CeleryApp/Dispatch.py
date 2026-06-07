"""Encolar con error LIMPIO si el broker (redis) no está disponible.

Cuando se despacha una task (`.delay()` / `.apply_async()`) y redis no responde,
Celery/kombu lanzan un error de bajo nivel poco claro. `broker_guard()` lo convierte
en un `QueueUnavailableError` con un mensaje que explica qué falta (redis + worker) y
recuerda que existe el camino síncrono (p. ej. `Mail.send`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import redis.exceptions
from kombu.exceptions import OperationalError

from tequio.Core.Config import settings
from tequio.Core.Errors import DomainError


class QueueUnavailableError(DomainError):
    """No se pudo encolar porque el broker (redis) no está disponible (= 503).

    Hereda de `DomainError`: el handler global RFC 9457 lo rinde como
    `application/problem+json` (503 Service Unavailable) SOLO — el controller/job que
    despacha NO necesita `try/except ... raise HTTPException(503)`. Faro, no silencio:
    el broker caído sale como un error claro y observable, nunca un 500 técnico ni un drop mudo.
    """

    status_code = 503
    error_code = "queue_unavailable"
    title = "Queue unavailable"


@contextmanager
def broker_guard() -> Iterator[None]:
    """Envuelve un despacho a la cola y traduce fallos de conexión al broker en un
    `QueueUnavailableError` con mensaje accionable."""
    try:
        yield
    except (OperationalError, redis.exceptions.ConnectionError, OSError) as error:
        raise QueueUnavailableError(
            f"No se pudo encolar: el broker no responde en {settings.effective_broker_url!r}. "
            "Las operaciones ENCOLADAS necesitan el broker corriendo (BROKER_URL en .env, default redis) "
            "y un worker consumiendo (`queue work`). Si no quieres encolar, usa el camino SÍNCRONO "
            "(p. ej. `Mail.send` en vez de `Mail.queue`)."
        ) from error


def qualified_queue(name: str | None) -> str | None:
    """Aplica el QUEUE_NAMESPACE a un nombre de cola para convivir en un broker compartido.

    Resolvedor ÚNICO: todo call-site que pase un `queue=` explícito (enqueue_mail, Job.dispatch,
    el despacho de crons en `schedule run`, las entradas del beat, el worker `queue work --queue`)
    pasa por aquí, para que el prefijo se aplique en UN solo lugar y de forma consistente.

    Sin namespace (`settings.queue_namespace == ""`): pasa `name` TAL CUAL — comportamiento de
    siempre, 100% retrocompatible. Con namespace:
      - `None` -> `None`: la cola por defecto NO se prefija aquí; la aísla `task_default_queue`
        (= f"{ns}.celery", ver CeleryApp.py), que también cubre los despachos SIN `queue=`
        (events.handle, Mail.queue sin cola, jobs/crons a la default).
      - nombre explícito -> f"{ns}.{name}": el dev sigue tecleando 'emails' y termina en
        'miapp.emails' dentro del MISMO db (sobrevive en Redis Cluster, a diferencia del db-por-app).
    """
    ns = settings.queue_namespace
    if not ns or name is None:
        return name
    return f"{ns}.{name}"
