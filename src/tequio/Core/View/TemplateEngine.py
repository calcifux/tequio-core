"""Motor de templates Jinja2 del framework: el render de los CORREOS (= Blade del legacy).

Vive en `tequio.Core.View` (capa de templating reutilizable): el `Mailer`
(`Core/Mail`) lo consume para renderizar el HTML de cada correo. El motor en sí
es genérico (cualquier salida con plantilla podría usarlo), pero en tequio
worker-side su consumidor real es el correo.

Mapeo verificado contra las plantillas de correo del legacy:

  • `@extends('emails.trans.master')`     →  `{% extends "Emails/Trans/master.html.j2" %}`
  • `@yield('content')` / `@section`       →  `{% block content %}{% endblock %}`
  • `@include('emails.trans.footer.x')`   →  `{% include "Emails/Trans/Footer/x.html.j2" %}`
  • `{!! __('ns.key', vars, locale) !!}`   →  `{{ t('ns.key', vars, locale) | safe }}`
  • `{{ $data->x ?? '----' }}`             →  `{{ data.x or '----' }}`

Mantenemos un único `Environment` en el proceso. Auto-escape ON para HTML (default
seguro); cuando una cadena trae HTML legítimo (típico de las traducciones del
legacy con `<strong>`, `<br>`), el template usa `| safe` — equivalente a `{!! !!}`.

Carpetas en PascalCase (Views/Emails/Trans/...) — convención del proyecto;
no heredamos el lowercase de Laravel.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
    StrictUndefined,
    select_autoescape,
)

from tequio.Core.Config import settings
from tequio.Core.Discovery import package_dir
from tequio.Core.Translate import t as default_translate

# Raíz del PAQUETE tequio (…/src/tequio/Core/View/TemplateEngine.py -> parents[2]).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Raíz ÚNICA de vistas compartidas del framework: src/tequio/Resources/Views. Todo se
# referencia relativo a aquí (convención Jinja): "Emails/Trans/master.html.j2".
_WEB_VIEWS_DIR = _PROJECT_ROOT / "Resources" / "Views"


def _module_views_dirs() -> dict[str, Path]:
    """Descubre las vistas POR MÓDULO: {prefijo: ruta} para cada
    `app/Modules/<X>/Resources/Views` que exista. El prefijo = nombre del módulo en
    minúsculas → los templates se referencian namespaced: "example/welcome.html.j2"
    (= `example::welcome` de Laravel). Self-contained: viajan con el módulo al extraerlo."""
    modules_root = package_dir(settings.modules_package)
    if modules_root is None or not modules_root.is_dir():
        return {}
    dirs: dict[str, Path] = {}
    for module_dir in sorted(modules_root.iterdir()):
        views = module_dir / "Resources" / "Views"
        if views.is_dir() and not module_dir.name.startswith("_"):
            dirs[module_dir.name.lower()] = views
    return dirs


def _build_loader(templates_dir: Path | None) -> BaseLoader:
    """Loader de Jinja. Con `templates_dir` explícito (tests) → un FileSystemLoader.
    Por defecto → ChoiceLoader: (1) PrefixLoader con las vistas namespaced de cada
    módulo ("example/welcome.html.j2"), (2) la raíz compartida `Views/` (todo relativo
    a aquí: "Emails/Trans/master.html.j2"). Convención 100% Jinja:
    ruta relativa a una raíz + prefijo por módulo; sin atajos especiales."""
    if templates_dir is not None:
        return FileSystemLoader(str(templates_dir))
    shared = FileSystemLoader(str(_WEB_VIEWS_DIR))
    module_loaders = {prefix: FileSystemLoader(str(path)) for prefix, path in _module_views_dirs().items()}
    # Orden de prioridad: vistas por-módulo (namespaced) > vistas del USUARIO
    # (USER_VIEWS_DIR, proyecto externo; puede sobreescribir layouts) > raíz del framework.
    chain: list[BaseLoader] = []
    if module_loaders:
        chain.append(PrefixLoader(module_loaders))
    if settings.user_views_dir and Path(settings.user_views_dir).is_dir():
        chain.append(FileSystemLoader(settings.user_views_dir))
    chain.append(shared)
    return ChoiceLoader(chain) if len(chain) > 1 else shared


class TemplateEngine:
    """Envuelve un `jinja2.Environment` con la función `t` (i18n) registrada
    como global, para que cualquier template pueda traducir sin imports.

    El loader por defecto combina (ChoiceLoader) las vistas POR MÓDULO
    (`Modules/<X>/Resources/Views`, namespaced "<x>/...") + `tequio/Resources/Views`
    (raíz default: layouts compartidos de correo, p. ej. `Emails/Trans/...`).
    Los tests pueden pasar `templates_dir` (un solo FileSystemLoader) y/o una función
    `t` propia (para fixturizar sin tocar i18nice).
    """

    def __init__(
        self,
        templates_dir: Path | None = None,
        translate_func: Callable[..., Any] | None = None,
        # `undefined`=StrictUndefined hace que una variable faltante REVIENTE en
        # lugar de renderizar vacío en silencio (los correos a deudores deben
        # fallar visiblemente en QA, no llegar con campos en blanco).
        strict_undefined: bool = True,
    ):
        self._env = Environment(
            loader=_build_loader(templates_dir),
            autoescape=select_autoescape(enabled_extensions=("html", "j2", "html.j2")),
            undefined=StrictUndefined if strict_undefined else None,  # type: ignore[arg-type]
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )
        # Registramos la función `t` como global del environment → todos los
        # templates ya tienen `{{ t(...) | safe }}` disponible sin importar nada.
        self._env.globals["t"] = translate_func or default_translate
        # `app_name` (la marca del proyecto, desde APP_NAME del .env) disponible como
        # global → los layouts genéricos pueden usar `{{ app_name }}` sin que el
        # Mailable lo pase en cada `context` (el footer firmado lo usa así).
        self._env.globals["app_name"] = settings.app_name

    def render(self, template_name: str, context: dict[str, object]) -> str:
        """Renderiza el template `template_name` con el `context` dado."""
        template = self._env.get_template(template_name)
        return template.render(**context)

    @property
    def environment(self) -> Environment:
        """Acceso de bajo nivel al Environment (filtros/globals adicionales).
        Lo exponemos para extensibilidad; el camino normal es `render()`.
        """
        return self._env


# Instancia compartida del proceso. Los consumidores (Mailer) la reciben por
# inyección; nadie debería tomar dependencia del global en hot paths.
template_engine = TemplateEngine()
