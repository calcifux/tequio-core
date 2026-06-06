"""Tests del contrato Mailable / MailContent.

Sin BD ni SMTP: solo la dataclass + el ABC. Validamos que la clase abstracta
no se pueda instanciar y que una subclase mínima construya un MailContent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tequio.Core.Mail.Mailable import Mailable, MailContent


def test_mail_content_defaults_to_empty_collections() -> None:
    content = MailContent(subject="Hola", template="hello.html.j2")

    assert content.context == {}
    assert content.inline_assets == {}
    assert content.attachments == []
    assert content.from_email is None
    assert content.from_name is None


def test_mail_content_keeps_inline_assets_and_attachments() -> None:
    content = MailContent(
        subject="X",
        template="t.html.j2",
        inline_assets={"logo": Path("/tmp/logo.png")},
        attachments=[Path("/tmp/doc.pdf")],
    )

    assert content.inline_assets == {"logo": Path("/tmp/logo.png")}
    assert content.attachments == [Path("/tmp/doc.pdf")]


def test_mailable_is_abstract_and_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Mailable()  # type: ignore[abstract]


def test_concrete_subclass_can_build_mail_content() -> None:
    class HelloMailable(Mailable):
        def __init__(self, name: str):
            self._name = name

        def build(self) -> MailContent:
            return MailContent(subject=f"Hola {self._name}", template="hello.html.j2", context={"name": self._name})

    content = HelloMailable("Calcifux").build()

    assert content.subject == "Hola Calcifux"
    assert content.template == "hello.html.j2"
    assert content.context == {"name": "Calcifux"}
