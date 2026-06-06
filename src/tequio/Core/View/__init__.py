"""Capa de templating (Jinja2) del framework, worker-side.

Solo expone el `TemplateEngine` (el motor que renderiza el HTML de los correos).
La capa WEB de vistas (View/negotiate/Vite/Pwa) NO vive aquí: tequio es worker-side
y solo necesita el motor para que el `Mailer` arme los correos.
"""

from __future__ import annotations

from tequio.Core.View.TemplateEngine import TemplateEngine, template_engine

__all__ = ["TemplateEngine", "template_engine"]
