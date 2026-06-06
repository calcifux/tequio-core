"""Mediator (command bus 1:1, = `IRequestHandler` de MediatR / un command bus de Laravel).

Mapea un TIPO de comando a UN handler y delega. El comando es una intención que TÚ envías
explícitamente y de la que esperas un resultado; contrasta con el [[Observer]], que reacciona
a un hecho 1:N sin retorno. Sirve para sacar un caso de uso del controller y reusarlo
transport-neutral (HTTP, CLI, Job).

KISS deliberado: NO hay base genérica `Handler[C, R]` (forzaría `cast` que pelea con mypy
strict); un handler es cualquier clase con `.handle(command)`. Tampoco hay pipelines/behaviors
ni multi-handler — eso sería un MediatR completo (framework dentro del framework). Si solo
vas a llamar a un service, llama al service: no metas un comando de adorno.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tequio.Core.Errors import HandlerNotFoundError

# Registro 1:1 comando -> handler, a nivel de módulo (mismo molde que Console._REGISTRY).
_HANDLERS: dict[type, type] = {}


def handles(command_type: type) -> Callable[[type], type]:
    """Marca una clase como el handler de `command_type` y la auto-registra al importarse.

    Uso:
        @handles(CompleteTask)
        class CompleteTaskHandler:
            def handle(self, command: CompleteTask) -> Task: ...
    """

    def _register(handler_cls: type) -> type:
        _HANDLERS[command_type] = handler_cls
        return handler_cls

    return _register


def send(command: object) -> Any:  # noqa: ANN401 — el retorno depende del handler
    """Envía un comando a su handler (= `Send` de MediatR) y devuelve su resultado. Síncrono.

    Se llama `send` (no `dispatch`) para no chocar con `Events.dispatch` y marcar la
    diferencia: aquí ENVÍAS una intención 1:1 y esperas retorno; allá DISPARAS un hecho 1:N
    sin retorno. Sin handler registrado = bug de programación: lanza `HandlerNotFoundError`
    (status 500), que los handlers globales rinden como problem+json sin código nuevo.
    """
    handler_cls = _HANDLERS.get(type(command))
    if handler_cls is None:
        raise HandlerNotFoundError(command_type=type(command).__name__)
    return handler_cls().handle(command)


def registered_handlers() -> dict[type, type]:
    """Los handlers registrados (introspección + tests)."""
    return dict(_HANDLERS)


def reset_handlers() -> None:
    """Limpia el registro (SOLO para tests). Espejo de reset_seeders()."""
    _HANDLERS.clear()
