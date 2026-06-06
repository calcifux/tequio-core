"""Tests del discovery del worker: las tasks del FRAMEWORK quedan registradas.

Regresión del bug cazado en la primera prueba real (2026-06-06): el worker recibía
el mensaje en la cola `emails` pero respondía "Received unregistered task of type
'mail.send'" — `_discover_modules` importaba los árboles de los módulos y Events,
pero a nadie le tocaba importar `Core/Mail/Tasks.py`. El correo encolado se
DESCARTABA en silencio (para el remitente, el encolado fue exitoso).
"""

from __future__ import annotations

from tequio.Core.CeleryApp import celery_app
from tequio.Core.CeleryApp.CeleryApp import _discover_modules


def test_worker_discovery_registers_framework_tasks() -> None:
    """Tras el discovery del arranque (worker/beat), las tasks del framework
    existen en el registro de Celery: sin esto, un mensaje encolado a `mail.send`
    o `events.handle` se descarta con "unregistered task"."""
    _discover_modules(celery_app)

    assert "mail.send" in celery_app.tasks  # Core/Mail/Tasks.py (la que faltaba)
    assert "events.handle" in celery_app.tasks  # Core/Events/Tasks.py


def test_worker_discovery_registers_demo_module_tasks() -> None:
    """Las tasks de los MÓDULOS también entran por el mismo discovery (árbol
    recursivo): el job y el cron del Demo quedan ejecutables en el worker."""
    _discover_modules(celery_app)

    assert "demo.export_notes" in celery_app.tasks
    assert "demo.daily_digest" in celery_app.tasks
