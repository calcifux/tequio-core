"""Tests de la task `mail.send`: política de reintentos ante fallos transitorios.

Sin redis ni SMTP reales: el resolver del Mailable y el mailer se monkeypatchean
con fakes, y los reintentos se ejercitan en modo `task_always_eager` (síncrono, sin
worker), con el backoff anulado para que el test no duerma. Mismo patrón de fakes +
monkeypatch del resto de la suite (cero BD/red).
"""

from __future__ import annotations

import smtplib
from typing import Any

from pytest import MonkeyPatch, raises

from tequio.Core.CeleryApp import celery_app
from tequio.Core.Config import settings
from tequio.Core.Mail import Tasks
from tequio.Core.Mail.Mailable import Mailable, MailContent
from tequio.Core.Mail.Tasks import enqueue_mail, send_mail_task


class _FakeMailable:
    """Mailable mínimo. El resolver se monkeypatchea para devolver esta clase, así no
    dependemos de importar un Mailable real por ruta dotted."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def build(self) -> MailContent:
        return MailContent(subject=f"Hola {self.kwargs.get('name', '')}", template="t.j2")


class _RecordingMailer:
    """Mailer fake: registra cada envío y falla las primeras `fail_times` veces con un
    error TRANSITORIO (simula un SMTP que se cae y luego se recupera)."""

    def __init__(self, fail_times: int = 0) -> None:
        self.calls: list[tuple[MailContent, list[str]]] = []
        self._fail_times = fail_times

    def send(
        self,
        content: MailContent,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> None:
        self.calls.append((content, to))
        if len(self.calls) <= self._fail_times:
            raise smtplib.SMTPServerDisconnected("SMTP caído (transitorio)")


def _patch_resolver_and_mailer(monkeypatch: MonkeyPatch, mailer: _RecordingMailer) -> None:
    monkeypatch.setattr(Tasks, "default_mailer", mailer)
    monkeypatch.setattr(Tasks, "_resolve_mailable_class", lambda _path: _FakeMailable)


def _force_eager_without_sleeping(monkeypatch: MonkeyPatch, *, max_retries: int) -> None:
    """Ejecuta la task en el acto (sin worker) y anula el backoff para no dormir."""
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(send_mail_task, "max_retries", max_retries)
    monkeypatch.setattr(send_mail_task, "retry_backoff", False)
    monkeypatch.setattr(send_mail_task, "retry_jitter", False)
    monkeypatch.setattr(send_mail_task, "default_retry_delay", 0)


def test_mail_send_task_has_retry_policy() -> None:
    """La task declara reintentos SOLO para errores transitorios, con backoff + jitter
    (defaults framework-wide vía retry_policy/.env)."""
    assert send_mail_task.max_retries == settings.task_max_retries
    assert smtplib.SMTPException in send_mail_task.autoretry_for
    assert ConnectionError in send_mail_task.autoretry_for
    assert TimeoutError in send_mail_task.autoretry_for
    assert send_mail_task.retry_backoff == settings.task_retry_backoff
    assert send_mail_task.retry_backoff_max == settings.task_retry_backoff_max
    assert send_mail_task.retry_jitter is True


def test_mail_send_task_happy_path_sends_once(monkeypatch: MonkeyPatch) -> None:
    """Camino feliz: reinstancia el Mailable y manda exactamente una vez."""
    mailer = _RecordingMailer()
    _patch_resolver_and_mailer(monkeypatch, mailer)

    send_mail_task(
        mailable_class_path="x.Y",
        mailable_kwargs={"name": "Memo"},
        to=["a@example.com"],
    )

    assert len(mailer.calls) == 1
    content, to = mailer.calls[0]
    assert to == ["a@example.com"]
    assert content.subject == "Hola Memo"


def test_mail_send_task_retries_until_exhausted(monkeypatch: MonkeyPatch) -> None:
    """SMTP siempre caído: reintenta hasta max_retries y la task queda en FALLO."""
    _force_eager_without_sleeping(monkeypatch, max_retries=2)
    mailer = _RecordingMailer(fail_times=99)
    _patch_resolver_and_mailer(monkeypatch, mailer)

    result = send_mail_task.apply(kwargs={"mailable_class_path": "x.Y", "mailable_kwargs": {}, "to": ["a@example.com"]})

    # 1 intento + 2 reintentos = 3 ejecuciones; agotados los reintentos, la task falla.
    assert len(mailer.calls) == 3
    assert result.failed()


def test_mail_send_task_recovers_within_budget(monkeypatch: MonkeyPatch) -> None:
    """SMTP se recupera dentro del presupuesto de reintentos: el correo SÍ se envía."""
    _force_eager_without_sleeping(monkeypatch, max_retries=3)
    mailer = _RecordingMailer(fail_times=2)  # falla 2 veces, al 3er intento envía
    _patch_resolver_and_mailer(monkeypatch, mailer)

    result = send_mail_task.apply(kwargs={"mailable_class_path": "x.Y", "mailable_kwargs": {}, "to": ["a@example.com"]})

    assert len(mailer.calls) == 3
    assert result.successful()


# ---------------------------------------------------------------- guard de init_kwargs


class _NecesitaArgs(Mailable):
    """Mailable cuyo __init__ EXIGE un argumento (como el DailyDigestMailable real)."""

    def __init__(self, total: int) -> None:
        self._total = total

    def build(self) -> MailContent:
        return MailContent(subject=f"{self._total}", template="t.j2")


class _SinArgs(Mailable):
    """Mailable sin argumentos: el único caso donde omitir init_kwargs es válido."""

    def build(self) -> MailContent:
        return MailContent(subject="hola", template="t.j2")


def test_enqueue_without_init_kwargs_fails_fast_when_init_requires_args() -> None:
    """Regresión (bug real 2026-06-06): el digest encolaba sin init_kwargs y el worker
    tronaba con TypeError al reinstanciar — fallo asíncrono invisible para el remitente.
    El guard revienta AL ENCOLAR, con instrucción accionable, ANTES de tocar el broker."""
    with raises(ValueError, match="init_kwargs"):
        enqueue_mail(_NecesitaArgs(total=7), to=["a@example.com"])


def test_enqueue_without_init_kwargs_passes_for_no_arg_mailables(monkeypatch: MonkeyPatch) -> None:
    """Un Mailable sin args sí puede encolarse sin init_kwargs (el worker lo reinstancia
    con kwargs vacíos). Capturamos apply_async para no tocar redis."""
    captured: dict[str, Any] = {}

    def _capture(*args: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(Tasks.send_mail_task, "apply_async", _capture)

    enqueue_mail(_SinArgs(), to=["a@example.com"])

    assert captured["kwargs"]["mailable_kwargs"] == {}


# ---------------------------------------------------------------- QUEUE_NAMESPACE (bus compartido)


def test_enqueue_mail_qualifies_queue_with_namespace(monkeypatch: MonkeyPatch) -> None:
    """Con QUEUE_NAMESPACE, la cola del correo se prefija ('emails' -> 'miapp.emails') para
    que dos apps en el mismo broker no compartan la cola de correos. Capturamos apply_async."""
    monkeypatch.setattr(settings, "queue_namespace", "miapp")
    captured: dict[str, Any] = {}
    monkeypatch.setattr(Tasks.send_mail_task, "apply_async", lambda *a, **k: captured.update(k))

    enqueue_mail(_SinArgs(), to=["a@example.com"], queue="emails")

    assert captured["queue"] == "miapp.emails"


def test_enqueue_mail_leaves_queue_intact_without_namespace(monkeypatch: MonkeyPatch) -> None:
    """Sin namespace: la cola viaja tal cual ('emails') — retrocompatible."""
    monkeypatch.setattr(settings, "queue_namespace", "")
    captured: dict[str, Any] = {}
    monkeypatch.setattr(Tasks.send_mail_task, "apply_async", lambda *a, **k: captured.update(k))

    enqueue_mail(_SinArgs(), to=["a@example.com"], queue="emails")

    assert captured["queue"] == "emails"
