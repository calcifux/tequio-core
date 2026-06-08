"""Task de Celery `events.handle` + helper `enqueue_observer` (rama ENCOLADA de los eventos).

Este módulo es el LAZY BOUNDARY: solo se importa cuando un evento se encola (desde
`Dispatch._dispatch_one`) o cuando el worker lo carga. Importa Celery (y por ende redis/kombu)
arriba, así que `Core.Events.__init__` NO lo re-exporta: un proyecto que nunca encola
observers jamás jala redis (mismo trato que `Core/Mail/Tasks.py`).

Contrato de serialización (= `SerializesModels` de Laravel): el evento debe ser un
`@dataclass` de primitivos planos. Se viaja (observer_path, event_path, event_kwargs) y el
worker reconstruye observer + evento desde su ruta dotted y corre `handle()`. NUNCA se
serializa una instancia ORM ni una sesión.
"""

from __future__ import annotations

import importlib
from typing import Any

from tequio.Core.CeleryApp import broker_guard, celery_app, qualified_queue
from tequio.Core.Config import settings
from tequio.Core.Events.Observer import Observer


@celery_app.task(name="events.handle")
def _handle_event_task(observer_path: str, event_path: str, event_kwargs: dict[str, Any]) -> None:
    """Corre en el WORKER: re-resuelve observer + evento desde primitivos y ejecuta handle()."""
    observer_cls = _import_symbol(observer_path)
    event_cls = _import_symbol(event_path)
    observer_cls().handle(event_cls(**event_kwargs))


def enqueue_observer(observer_cls: type[Observer], event: object) -> None:
    """Encola la ejecución de `observer_cls.handle(event)` en Celery.

    El evento debe ser un dataclass de primitivos (sus campos viajan como kwargs JSON y se
    reconstruyen en el worker). `broker_guard`: si el broker no responde, lanza
    `QueueUnavailableError` (el caller cae a ejecución síncrona)."""
    payload: dict[str, Any] = dict(vars(event))
    # EVENTS_QUEUE vacío => queue=None => cae en task_default_queue ({ns}.celery), como siempre.
    # Con valor => su cola propia {ns}.events (focalización para observabilidad sin proceso extra).
    queue = qualified_queue(settings.events_queue) if settings.events_queue else None
    with broker_guard():
        _handle_event_task.apply_async(
            kwargs={
                "observer_path": f"{observer_cls.__module__}.{observer_cls.__qualname__}",
                "event_path": f"{type(event).__module__}.{type(event).__qualname__}",
                "event_kwargs": payload,
            },
            queue=queue,
        )


def _import_symbol(dotted: str) -> Any:  # noqa: ANN401 — resuelve una clase arbitraria por ruta
    """Importa el símbolo en la ruta dotted (`paquete.modulo.Clase`)."""
    module_path, _, name = dotted.rpartition(".")
    if not module_path or not name:
        raise ValueError(f"Ruta de símbolo inválida: {dotted!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)
