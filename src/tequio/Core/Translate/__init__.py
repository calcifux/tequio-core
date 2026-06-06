"""Utilidad transversal de traducción (i18n). Cubre mailables, errores de
Pydantic, mensajes de API y cualquier otra cadena visible al usuario.

Reemplaza el `I18n` custom que vivía en `app/Core/Mail/` (era boilerplate):
ahora delegamos en `i18nice` (fork mantenido de `python-i18n`), y mantenemos
solo un wrapper liviano con la firma `t(key, vars, locale)` que ya usaban los
templates Jinja2 y los Mailables.
"""

from __future__ import annotations

from tequio.Core.Translate.I18n import current_locale, set_request_locale, t

__all__ = ["current_locale", "set_request_locale", "t"]
