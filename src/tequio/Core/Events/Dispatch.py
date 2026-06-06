"""`dispatch(event)`: dispara un evento a sus observers, con transporte adaptativo.

Regla de routing (decisión del dueño, KISS): **si hay broker disponible, el observer corre
en el worker (async); si no, corre síncrono inline.** Sin flags por-observer. El import de
Celery es PEREZOSO (mismo patrón que la rama encolada de Tasks.py), así un proyecto que nunca
encola observers no jala redis. Best-effort POR observer: uno que falla no tumba a los demás ni
al caller (un efecto secundario no debe romper la operación de negocio).
"""

from __future__ import annotations

from loguru import logger

from tequio.Core.Config import settings
from tequio.Core.Events.Observer import Observer, registered_observers


def dispatch(event: object) -> None:
    """Dispara `event` a cada Observer cuyo `observes` matchee su tipo (o sea None). 1:N."""
    for observer_cls in registered_observers():
        if observer_cls.observes not in (None, type(event)):
            continue
        try:
            _dispatch_one(observer_cls, event)
        except Exception:  # noqa: BLE001 — best-effort: un observer no debe romper al caller
            # Tenet "nunca falla en silencio": en dev/test (EVENTS_STRICT) RE-LANZA para que el
            # bug del observer truene fuerte; en prod loguea RUIDOSO (ERROR + traceback) y sigue
            # (un efecto secundario no debe tumbar la operación de negocio), pero NUNCA en silencio.
            if settings.events_strict:
                raise
            logger.exception(
                "Events | observer {o} falló manejando {e}", o=observer_cls.__name__, e=type(event).__name__
            )


def _dispatch_one(observer_cls: type[Observer], event: object) -> None:
    """Encola el observer si hay broker; si no, lo corre síncrono. Import lazy de Celery
    (mismo patrón que la rama encolada de Tasks.py): sin esta rama, Events no jala redis al
    importarse."""
    from tequio.Core.CeleryApp import QueueUnavailableError
    from tequio.Core.Events.Tasks import enqueue_observer

    try:
        enqueue_observer(observer_cls, event)  # broker disponible -> async, sobre el broker
    except QueueUnavailableError:
        observer_cls().handle(event)  # sin broker -> síncrono inline
