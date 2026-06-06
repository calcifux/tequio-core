"""Test del rechazo PARCIAL de destinatarios en el Mailer SMTP (tenet "nunca falla en silencio").

`smtp.send_message` NO lanza cuando solo ALGUNOS destinatarios rebotan en RCPT TO; devuelve un dict
de rechazados. El Mailer ahora lo captura, loguea y relanza `SMTPRecipientsRefused` en vez de
perder el fallo remoto parcial. Sin red: se monkeypatchea `smtplib.SMTP` con un fake.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

import pytest
from pytest import MonkeyPatch

from tequio.Core.Config import settings
from tequio.Core.Mail.Mailer import Mailer


class _FakeSMTP:
    """SMTP fake cuyo `send_message` simula un rechazo PARCIAL (un destinatario rebotado)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *args: Any) -> None: ...

    def ehlo(self) -> None: ...

    def starttls(self) -> None: ...

    def login(self, username: str, password: str) -> None: ...

    def send_message(self, message: EmailMessage, to_addrs: list[str] | None = None) -> dict[str, tuple[int, bytes]]:
        return {"bad@x.com": (550, b"No such user")}


def test_partial_recipient_refusal_is_raised_not_swallowed(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mail_encryption", "none")
    monkeypatch.setattr(settings, "mail_username", "")  # sin login
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    message = EmailMessage()
    message["Subject"] = "x"

    with pytest.raises(smtplib.SMTPRecipientsRefused):
        Mailer._dispatch(message, recipients=["ok@x.com", "bad@x.com"])
