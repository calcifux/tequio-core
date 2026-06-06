"""Correos del demo (un archivo por clase, convención de los `make:*`).

Demuestra el patrón "plantilla general firmada + correos específicos encima" (estilo milpa):

  - `DemoMailable` es la BASE: aporta la FIRMA común (`sender_*`) que consume el layout
    firmado COMPARTIDO de tequio (`Emails/Trans/mastersigned.html.j2` → header + content +
    footer firmado + aviso de privacidad). NO implementa `build()`; expone `_signed(...)`.
  - `DailyDigestMailable` es el correo CONCRETO: solo define su `subject`, su `template`
    (que `{% extends %}` el firmado) y su contexto. Lo manda el cron `demo.daily_digest`.

A diferencia de milpa, aquí NO hay dueño/usuario (worker-side, sin Auth): el digest es un
resumen ANÓNIMO con el conteo total de notas, y el subject es monolingüe en español con ese
conteo (adaptación mínima; el plumbing i18n de `t()` está disponible si se quisiera espejar
el correo multilingüe de milpa, pero el digest no lo necesita).

(En un proyecto real, `sender_*` vendría del remitente configurado, no hardcodeado.)
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tequio.Core.Mail import Mailable, MailContent


class DemoMailable(Mailable):
    """Base abstracta de los correos del demo. NO implementa `build()` (las subclases sí);
    expone `_signed(...)` que inyecta la firma común en el contexto del layout firmado."""

    _SIGNER: ClassVar[dict[str, str]] = {
        "sender_name": "Equipo tequio",
        "sender_phone": "+52 55 0000 0000",
        "sender_email": "no-reply@tequio.dev",
        "sender_address": "CDMX, México",
    }
    # Logo de marca: el layout firmado (mastersigned) renderiza <img src="cid:logo"> si viene
    # `logo_cid`. Se EMBEBE por CID (no URL) para que se vea sin conexión y sin hotlinking.
    # Este archivo vive en `Mail/` dentro del módulo, así que se sube un nivel (`parent.parent`)
    # para llegar a `Resources/Static/logo.png`, junto a las plantillas del módulo.
    _LOGO: ClassVar[Path] = Path(__file__).resolve().parent.parent / "Resources" / "Static" / "logo.png"

    def _signed(self, *, subject: str, template: str, context: dict[str, object] | None = None) -> MailContent:
        """Arma un `MailContent` con la firma común + el LOGO embebido + el contexto del correo."""
        ctx: dict[str, object] = {**self._SIGNER, **(context or {})}
        inline: dict[str, Path] = {}
        if self._LOGO.is_file():  # best-effort: si falta el logo, el correo sale igual (sin marca)
            ctx["logo_cid"] = "logo"
            inline["logo"] = self._LOGO
        return MailContent(subject=subject, template=template, context=ctx, inline_assets=inline)


class DailyDigestMailable(DemoMailable):
    """Resumen diario ANÓNIMO: "hoy hay N notas en total". Lo manda el cron `demo.daily_digest`.

    Sin dueño/usuario (worker-side): el único dato es el conteo `total`. Subject monolingüe en
    español con el conteo; cuerpo en `demo/emails/digest.html.j2`, que extiende el firmado.
    """

    def __init__(self, total: int) -> None:
        self._total = total

    def build(self) -> MailContent:
        return self._signed(
            subject=f"Resumen diario: {self._total} notas en total",
            template="demo/emails/digest.html.j2",
            context={"total": self._total},
        )
