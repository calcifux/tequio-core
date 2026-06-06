"""Tests del Mailer (sin abrir conexión SMTP real).

Monkeypatcheamos `smtplib.SMTP` para capturar el mensaje y los destinatarios,
sin enviar nada por la red. Fakes y monkeypatch, cero BD/red.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from tequio.Core.Mail.Mailable import MailContent
from tequio.Core.Mail.Mailer import Mailer
from tequio.Core.View.TemplateEngine import TemplateEngine

_PLACEHOLDER_RE = re.compile(r"%\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _fake_translate(catalog: dict[str, str]) -> Any:
    """Translate-func fake con interpolación `%{name}` (= sintaxis i18nice).
    Si la key no existe → devuelve la key (mismo contrato que el wrapper real).
    """

    def fake_t(key: str, variables: dict[str, Any] | None = None, locale: str | None = None) -> str:
        template = catalog.get(key)
        if template is None:
            return key
        return _PLACEHOLDER_RE.sub(lambda match: str((variables or {}).get(match.group(1), match.group(0))), template)

    return fake_t


class _FakeSmtp:
    """Reemplazo de `smtplib.SMTP` que captura lo que se le pasa."""

    instances: list[_FakeSmtp] = []  # acumulador para inspección desde el test

    def __init__(self, host: str = "", port: int = 0, timeout: int = 0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_called = False
        self.login_called: tuple[str, str] | None = None
        self.sent_messages: list[tuple[Any, list[str]]] = []
        _FakeSmtp.instances.append(self)

    def __enter__(self) -> _FakeSmtp:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def ehlo(self) -> None:
        pass

    def starttls(self) -> None:
        self.starttls_called = True

    def login(self, username: str, password: str) -> None:
        self.login_called = (username, password)

    def send_message(self, message: Any, to_addrs: list[str] | None = None) -> None:
        self.sent_messages.append((message, to_addrs or []))


@pytest.fixture(autouse=True)
def _reset_fake_smtp() -> None:
    _FakeSmtp.instances.clear()


def _build_engine(tmp_path: Path) -> TemplateEngine:
    """Templates + translate fake mínimos para que el Mailer pueda renderizar."""
    views = tmp_path / "views"
    views.mkdir()
    (views / "hello.html.j2").write_text(
        '<p>{{ t("emails/test.hello", {"name": name}, "es") | safe }}</p>',
        encoding="utf-8",
    )
    translate = _fake_translate({"emails/test.hello": "Hola %{name}"})
    return TemplateEngine(templates_dir=views, translate_func=translate)


def test_send_renders_template_and_dispatches_to_smtp(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tequio.Core.Mail.Mailer.smtplib.SMTP", _FakeSmtp)
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_encryption", "")
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_username", "")

    mailer = Mailer(engine=_build_engine(tmp_path))
    mailer.send(
        MailContent(subject="Hola", template="hello.html.j2", context={"name": "Calcifux"}),
        to=["destino@yopmail.com"],
    )

    assert len(_FakeSmtp.instances) == 1
    fake = _FakeSmtp.instances[0]
    assert fake.starttls_called is False  # sin cifrado
    assert fake.login_called is None  # sin auth
    assert len(fake.sent_messages) == 1
    message, recipients = fake.sent_messages[0]
    assert recipients == ["destino@yopmail.com"]
    assert message["Subject"] == "Hola"
    # El HTML rendereado debe contener el saludo interpolado.
    html_part = next(part for part in message.iter_parts() if part.get_content_subtype() == "html")
    assert "Hola Calcifux" in html_part.get_content()


def test_send_with_tls_calls_starttls(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tequio.Core.Mail.Mailer.smtplib.SMTP", _FakeSmtp)
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_encryption", "tls")
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_username", "user")
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_password", "secret")

    mailer = Mailer(engine=_build_engine(tmp_path))
    mailer.send(
        MailContent(subject="Con TLS", template="hello.html.j2", context={"name": "Calcifux"}),
        to=["x@yopmail.com"],
    )

    fake = _FakeSmtp.instances[0]
    assert fake.starttls_called is True
    assert fake.login_called == ("user", "secret")


def test_send_includes_cc_and_bcc_in_recipients(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tequio.Core.Mail.Mailer.smtplib.SMTP", _FakeSmtp)
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_encryption", "")
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_username", "")

    mailer = Mailer(engine=_build_engine(tmp_path))
    mailer.send(
        MailContent(subject="Con CC y BCC", template="hello.html.j2", context={"name": "Calcifux"}),
        to=["a@yopmail.com"],
        cc=["b@yopmail.com"],
        bcc=["c@yopmail.com"],
    )

    fake = _FakeSmtp.instances[0]
    _message, recipients = fake.sent_messages[0]
    # SMTP RCPT TO debe incluir TODOS (BCC también) — el header no, pero el envelope sí.
    assert set(recipients) == {"a@yopmail.com", "b@yopmail.com", "c@yopmail.com"}
    # El header Cc sí debe estar; el header Bcc NO (esa es la diferencia de Bcc vs Cc).
    assert _message["Cc"] == "b@yopmail.com"
    assert _message["Bcc"] is None


def test_send_uses_mailable_from_overrides_settings_default(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tequio.Core.Mail.Mailer.smtplib.SMTP", _FakeSmtp)
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_encryption", "")
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_username", "")
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_from_email", "default@aklara.com")
    monkeypatch.setattr("tequio.Core.Mail.Mailer.settings.mail_from_name", "Default")

    mailer = Mailer(engine=_build_engine(tmp_path))
    mailer.send(
        MailContent(
            subject="Override From",
            template="hello.html.j2",
            context={"name": "Calcifux"},
            from_email="cobranza@aklara.com",
            from_name="Cobranza",
        ),
        to=["x@yopmail.com"],
    )

    fake = _FakeSmtp.instances[0]
    message, _ = fake.sent_messages[0]
    # El From debe ser el del MailContent, no el default de settings.
    assert "cobranza@aklara.com" in message["From"]
    assert "Cobranza" in message["From"]
