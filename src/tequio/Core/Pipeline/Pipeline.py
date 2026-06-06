"""Pipeline (= `Illuminate\\Pipeline` de Laravel; modelo cebolla / middleware).

Pasa UN objeto por una serie de etapas (`pipes`) en orden; cada etapa recibe el objeto y un
`next` y decide si sigue (llama `next(passable)`) o corta (no lo llama). Contrasta con el
[[Mediator]] (enruta UNA intención a UN handler) y con los [[Observer]] (1:N fire-and-forget):
aquí UN objeto fluye por VARIAS etapas que lo transforman o lo detienen.

Utilidad PURA: cero dependencias de tequio, cero discovery. Los pipes y su orden se pasan
EXPLÍCITOS a `.through([...])` (como en Laravel) — no se auto-descubren. Es la pieza reusable
que un dev no quiere re-implementar por proyecto (el encadenamiento de closures con `reduce`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import reduce
from typing import Any, Protocol


class Pipe(Protocol):
    """Una etapa del pipeline. Recibe el objeto y `next`; llama `next(passable)` para seguir,
    o devuelve sin llamarlo para cortar el flujo."""

    def handle(self, passable: Any, next: Callable[[Any], Any]) -> Any: ...  # noqa: A002 — `next` calca a Laravel


class Pipeline:
    """Encadena pipes alrededor de un destino final. API fluida estilo Laravel."""

    def __init__(self) -> None:
        self._passable: Any = None
        self._pipes: list[Pipe] = []

    def send(self, passable: Any) -> Pipeline:  # noqa: ANN401 — pasa cualquier objeto
        """Fija el objeto que viajará por el pipeline."""
        self._passable = passable
        return self

    def through(self, pipes: Sequence[Pipe]) -> Pipeline:
        """Fija las etapas, en orden de ejecución. `Sequence` (covariante) acepta una
        `list[PipeConcreto]` sin pelear con la invarianza de `list`."""
        self._pipes = list(pipes)
        return self

    def then(self, destination: Callable[[Any], Any]) -> Any:  # noqa: ANN401
        """Ejecuta el pipeline y llama `destination` al final (el "núcleo de la cebolla").

        Construye la cadena de afuera hacia adentro con `reduce`: cada pipe envuelve al
        siguiente, de modo que el primero de la lista corre primero.
        """
        chain: Callable[[Any], Any] = reduce(
            lambda nxt, pipe: lambda passable: pipe.handle(passable, nxt),
            reversed(self._pipes),
            destination,
        )
        return chain(self._passable)

    def then_return(self) -> Any:  # noqa: ANN401
        """Ejecuta el pipeline devolviendo el objeto tal cual sale de la última etapa."""
        return self.then(lambda passable: passable)
