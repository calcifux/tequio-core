"""Tests del MAIL_DRIVER: los drivers `log`/`null` NUNCA abren una conexión SMTP.

Es lo que hace seguro el fallback cross-platform: sin red, sin sorpresas. Si el
Mailer intentara conectar con estos drivers, el fake `_boom` rompería el test.

Construimos un `MailContent` directo (sin depender de ningún Mailable concreto:
los Mailables demo viven en Modules/Demo, y este es un test de Core). El template
es TRIVIAL y vive en `tmp_path` con su propio engine: este test de Core NO debe
depender de los layouts compartidos de correo (esos los ejercita el render del Demo).
"""

from __future__ import annotations

import smtplib
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from tequio.Core.Config import settings
from tequio.Core.Mail.Mailable import MailContent
from tequio.Core.Mail.Mailer import Mailer
from tequio.Core.View.TemplateEngine import TemplateEngine


def _boom(*args: Any, **kwargs: Any) -> None:
    raise AssertionError("No debió abrirse una conexión SMTP con este driver.")


def _engine_with_trivial_template(tmp_path: Path) -> TemplateEngine:
    """Engine aislado con un template mínimo: el driver no necesita un layout real,
    solo algo que renderice (StrictUndefined-safe con context vacío)."""
    views = tmp_path / "views"
    views.mkdir()
    (views / "smoke.html.j2").write_text("<p>smoke</p>", encoding="utf-8")
    return TemplateEngine(templates_dir=views)


@pytest.mark.parametrize("driver", ["null", "array", "log"])
def test_non_smtp_drivers_never_open_a_connection(driver: str, monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "mail_driver", driver)
    monkeypatch.setattr(smtplib, "SMTP", _boom)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _boom)

    content = MailContent(subject="smoke", template="smoke.html.j2", context={})
    # No debe lanzar: el correo se descarta (null/array) o se escribe al log (log).
    Mailer(engine=_engine_with_trivial_template(tmp_path)).send(content, to=["a@x.com"])
