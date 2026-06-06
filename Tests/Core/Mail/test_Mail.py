"""Tests de la facade `Mail` (Mail.send síncrono / Mail.queue asíncrono).

DB-free y SIN redis: para `send` monkeypatcheamos el `mailer`; para `queue`
monkeypatcheamos `enqueue_mail` (la maquinaria de Celery no se ejecuta). Verifican
que la facade DELEGUE bien en cada camino.
"""

from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

import tequio.Core.Mail.Tasks as tasks_module
from tequio.Core.Mail import Mail
from tequio.Core.Mail.Mailable import Mailable, MailContent
from tequio.Core.Mail.Mailer import mailer


class _FakeMailable(Mailable):
    """Mailable mínimo para el test (sin i18n ni templates reales)."""

    def build(self) -> MailContent:
        return MailContent(subject="Hola", template="x.html.j2", context={})


def test_send_is_synchronous_and_delegates_to_mailer(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        mailer,
        "send",
        lambda content, *, to, cc=None, bcc=None: captured.update(subject=content.subject, to=to),
    )

    Mail.send(_FakeMailable(), to=["a@x.com"])

    assert captured == {"subject": "Hola", "to": ["a@x.com"]}


def test_queue_delegates_to_enqueue_with_queue_and_kwargs(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        tasks_module,
        "enqueue_mail",
        lambda mailable, *, to, cc=None, bcc=None, queue=None, init_kwargs=None: captured.update(
            to=to, queue=queue, init_kwargs=init_kwargs
        ),
    )

    Mail.queue(_FakeMailable(), to=["a@x.com"], queue="emails", init_kwargs={"name": "Calcifux"})

    assert captured == {"to": ["a@x.com"], "queue": "emails", "init_kwargs": {"name": "Calcifux"}}


def test_queue_without_name_uses_the_default_queue(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        tasks_module,
        "enqueue_mail",
        lambda mailable, *, to, cc=None, bcc=None, queue=None, init_kwargs=None: captured.update(queue=queue),
    )

    Mail.queue(_FakeMailable(), to=["a@x.com"])  # sin --queue -> cola por defecto

    assert captured == {"queue": None}
