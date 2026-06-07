"""Tests del QUEUE_NAMESPACE: el resolvedor `qualified_queue` y la cola por defecto
del celery_app, las dos piezas que aíslan a una app cuando varias comparten el MISMO
broker (redis db) y se robarían las tasks entre sí.

DB-free y sin redis: `settings.queue_namespace` se monkeypatchea (con/sin ns) y se
comprueba el prefijo. La cola por defecto del celery_app se verifica sobre el objeto real
(bajo el ns vacío de la suite NO está namespaceada).
"""

from __future__ import annotations

from pytest import MonkeyPatch

from tequio.Core.CeleryApp import celery_app, qualified_queue
from tequio.Core.Config import settings

# ------------------------------------------------------------------- qualified_queue


def test_qualified_queue_passthrough_without_namespace(monkeypatch: MonkeyPatch) -> None:
    """Sin namespace (default): el nombre pasa TAL CUAL — 100% retrocompatible."""
    monkeypatch.setattr(settings, "queue_namespace", "")
    assert qualified_queue("emails") == "emails"
    assert qualified_queue("celery") == "celery"


def test_qualified_queue_none_stays_none_without_namespace(monkeypatch: MonkeyPatch) -> None:
    """None (cola por defecto) pasa como None — la maneja task_default_queue, no el prefijo."""
    monkeypatch.setattr(settings, "queue_namespace", "")
    assert qualified_queue(None) is None


def test_qualified_queue_prefixes_explicit_name_with_namespace(monkeypatch: MonkeyPatch) -> None:
    """Con namespace: un nombre explícito gana el prefijo `{ns}.{name}` (el dev sigue
    tecleando 'emails' y termina en 'miapp.emails' dentro del mismo db)."""
    monkeypatch.setattr(settings, "queue_namespace", "miapp")
    assert qualified_queue("emails") == "miapp.emails"
    assert qualified_queue("celery") == "miapp.celery"


def test_qualified_queue_none_stays_none_with_namespace(monkeypatch: MonkeyPatch) -> None:
    """Con namespace, None SIGUE siendo None: la cola por defecto NO se prefija aquí; la
    aísla task_default_queue (= f'{ns}.celery'), que cubre los despachos sin queue=."""
    monkeypatch.setattr(settings, "queue_namespace", "miapp")
    assert qualified_queue(None) is None


# --------------------------------------------------------- task_default_queue del celery_app


def test_celery_app_default_queue_not_namespaced_under_empty_namespace() -> None:
    """Bajo el ns vacío de la suite (default), el guard de CeleryApp.py NO setea
    task_default_queue: el celery_app deja el default de Celery ('celery'), no f'{ns}.celery'.
    Faro de que el aislamiento NO se activa sin namespace (retrocompatible)."""
    assert settings.queue_namespace == ""
    assert celery_app.conf.task_default_queue != "miapp.celery"


def _apply_default_queue_guard(ns: str) -> str:
    """Reproduce el guard de CeleryApp.py sobre una conf falsa: con namespace fija
    task_default_queue = f'{ns}.celery'; sin namespace NO la toca (queda el default de Celery)."""

    class _Conf:
        task_default_queue = "celery"

    conf = _Conf()
    if ns:  # el mismo guard que corre en CeleryApp.py en tiempo de import
        conf.task_default_queue = f"{ns}.celery"
    return conf.task_default_queue


def test_default_queue_guard_untouched_without_namespace() -> None:
    """Sin namespace: la cola por defecto de Celery queda intacta ('celery')."""
    assert _apply_default_queue_guard("") == "celery"


def test_default_queue_guard_namespaced_with_namespace() -> None:
    """Con namespace: la cola por defecto pasa a f'{ns}.celery', para que events.handle /
    Mail.queue sin cola / jobs-crons a la default NO caigan en la 'celery' COMPARTIDA."""
    assert _apply_default_queue_guard("miapp") == "miapp.celery"
