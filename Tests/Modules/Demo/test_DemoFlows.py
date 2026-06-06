"""Tests EJECUTABLES del flujo AUTO (evento → Observer → efecto), SIN BD ni red.

Cierra el gap pedagógico: prueban que `dispatch(NoteCreated(...))` llega al Observer y este produce
su efecto (el corazón auto-vs-manual del demo). En milpa el efecto era `Mail.send(...)` y el test
capturaba el Mailable; tequio es worker-side (sin Mail): el observer LOGUEA (loguru) la creación de
la nota, así que aquí capturamos el LOG en vez del correo.

Layout estilo make:*: el observer vive en `Modules/Demo/Observers/LogNoteCreated.py` (un archivo
por clase, agrupado en la carpeta `Observers/`). Y se renombró: antes `NotifyOwnerOnNoteCreated`
(avisaba al DUEÑO); el demo soltó el dueño junto con todo el rastro de Auth, así que ahora es
`LogNoteCreated` y solo loguea la creación.

La rama encolada se fuerza a síncrono monkeypatcheando `enqueue_observer` (igual que
test_EventDispatch); el observer se re-registra con reload tras `reset_observers` para no depender
del orden de la suite. La captura NO usa el `caplog` de pytest (loguru no propaga al logging stdlib
salvo intercept): el idiom de este repo es agregar un sink propio de loguru y quitarlo en teardown.

En milpa este archivo probaba además el aviso a admins (UserRegistered → NotifyAdminOnUserRegistered
→ Mail). Eso depende de User/UserRepository/Auth, EXCLUIDOS de tequio: el evento UserRegistered y su
observer no existen aquí, así que esos tests se eliminan.

El CRON `demo.daily_digest` VUELVE a mandar correo (tequio nació para que los crons puedan mandar):
aquí lo corremos con el driver `log` (default dev) y `smtplib.SMTP` saboteado con `_boom`, afirmando
que NO abre conexión SMTP y que el MIME se VUELCA al log. El conteo de notas (`NoteRepository().all()`)
toca BD, así que lo monkeypatcheamos a `[]` para mantener "sin BD". Se fuerza la rama síncrona
(`Mail.send`) haciendo que `Mail.queue` lance `QueueUnavailableError` (= no hay broker en tests).
"""

from __future__ import annotations

import importlib
import smtplib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from loguru import logger
from pytest import MonkeyPatch

import tequio.Core.Events.Tasks as events_tasks
import tequio.Modules.Demo.Crons.DailyDigestCron as demo_crons
import tequio.Modules.Demo.Observers.LogNoteCreated as demo_observers
from tequio.Core.CeleryApp import QueueUnavailableError
from tequio.Core.Config import settings
from tequio.Core.Events import Observer, dispatch, reset_observers
from tequio.Modules.Demo.Events import NoteCreated
from tequio.Modules.Demo.Repositories.NoteRepository import NoteRepository


@dataclass
class _OtroEvento:
    """Evento de otro tipo (no NoteCreated): el observer no debe reaccionar a él. En milpa este
    rol lo cumplía UserRegistered; aquí basta un dataclass cualquiera para probar el filtro por tipo."""

    cosa: int


def _no_broker(observer_cls: type[Observer], event: object) -> None:
    raise QueueUnavailableError("sin broker")  # fuerza el fallback síncrono del dispatch


@pytest.fixture(autouse=True)
def _clean_observers() -> Iterator[None]:
    reset_observers()
    yield
    reset_observers()


@pytest.fixture
def captured_logs(monkeypatch: MonkeyPatch) -> Iterator[list[str]]:
    """Captura los mensajes que loguea el observer (sin SMTP) y fuerza dispatch síncrono.

    Agrega un sink de loguru ADITIVO (no interfiere con los sinks de la app/conftest) que acumula
    el `message` ya formateado en una lista; lo quita en teardown para no filtrar entre tests.
    """
    messages: list[str] = []
    sink_id = logger.add(lambda msg: messages.append(msg.record["message"]), level="INFO", format="{message}")
    monkeypatch.setattr(events_tasks, "enqueue_observer", _no_broker)
    yield messages
    logger.remove(sink_id)


def test_note_created_logs_creation(captured_logs: list[str]) -> None:
    importlib.reload(demo_observers)  # re-registra LogNoteCreated tras el reset
    dispatch(NoteCreated(note_id=1, title="Mi nota"))

    assert len(captured_logs) == 1
    message = captured_logs[0]
    assert "Mi nota" in message  # el título de la nota viaja en el log
    assert "1" in message  # el id de la nota también


def test_observer_ignores_events_of_other_type(captured_logs: list[str]) -> None:
    importlib.reload(demo_observers)  # solo el observer de NoteCreated está registrado
    dispatch(_OtroEvento(cosa=1))
    assert captured_logs == []  # observes=NoteCreated no matchea _OtroEvento


# --------------------------------------------------------- cron del digest → correo (driver log)
def _boom_smtp(*args: Any, **kwargs: Any) -> None:
    raise AssertionError("El driver `log` NO debió abrir una conexión SMTP.")


def test_daily_digest_cron_sends_mail_via_log_driver_without_smtp(monkeypatch: MonkeyPatch) -> None:
    """El cron `demo.daily_digest` manda el resumen por correo; con driver `log` el MIME se vuelca
    al log SIN tocar SMTP. Sin BD (NoteRepository().all() → []) ni broker (Mail.queue → falla,
    cae a Mail.send síncrono); `_boom` rompe el test si el driver `log` intentara conectar.
    """
    # Sin BD: el conteo del digest no debe tocar la base.
    monkeypatch.setattr(NoteRepository, "all", lambda self: [])
    # Driver log: el correo se VUELCA al log, sin SMTP.
    monkeypatch.setattr(settings, "mail_driver", "log")
    # Sabotaje: si el driver log intentara conectar, esto rompe el test.
    monkeypatch.setattr(smtplib, "SMTP", _boom_smtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _boom_smtp)

    # Sin broker en tests: forzamos la rama síncrona (Mail.send) que el cron toma en el except.
    def _no_broker_queue(*args: Any, **kwargs: Any) -> None:
        raise QueueUnavailableError("sin broker en tests")

    monkeypatch.setattr(demo_crons.Mail, "queue", staticmethod(_no_broker_queue))

    # Sink aditivo de loguru: capturamos el MIME que el driver `log` vuelca (mismo idiom del repo).
    messages: list[str] = []
    sink_id = logger.add(lambda msg: messages.append(msg.record["message"]), level="INFO", format="{message}")
    try:
        demo_crons.daily_digest()
    finally:
        logger.remove(sink_id)

    # El correo se volcó al log (el driver `log` loguea el MIME completo) con el subject del digest.
    dumped = "\n".join(messages)
    assert "Mailer[log]" in dumped  # el driver log dejó el correo NO enviado en el log
    assert "Resumen diario" in dumped  # el subject del digest viaja en el MIME volcado


def test_daily_digest_enqueues_to_the_emails_queue(monkeypatch: MonkeyPatch) -> None:
    """Camino ENCOLADO (con broker): el digest viaja a la cola de correos `emails`
    (= `->onQueue('emails')`), NO a la cola por defecto. Capturamos los kwargs de `Mail.queue`
    sin tocar redis (la maquinaria de Celery no se ejecuta) ni BD (NoteRepository().all() → [])."""
    monkeypatch.setattr(NoteRepository, "all", lambda self: [])

    captured: dict[str, Any] = {}

    def _capture_queue(*args: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(demo_crons.Mail, "queue", staticmethod(_capture_queue))

    demo_crons.daily_digest()

    assert captured.get("queue") == "emails"  # el digest encola en la cola de correos, no en la default
    # Regresión (bug real 2026-06-06): sin init_kwargs el worker NO puede reinstanciar el
    # Mailable (TypeError: missing 'total') y el correo muere asíncrono, invisible para el cron.
    assert captured.get("init_kwargs") == {"total": 0}  # = los args EXACTOS del __init__
