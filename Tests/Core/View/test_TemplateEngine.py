"""Tests unitarios del TemplateEngine Jinja2 (sin BD, sin SMTP).

Cada test crea sus templates en `tmp_path` y le pasa esa carpeta al
`TemplateEngine`. Para `t()`, inyectamos un `translate_func` propio del test
(no usamos el global de `tequio.Core.Translate`/i18nice — así los tests quedan
aislados del estado compartido del proceso).

Extracción worker-side: tequio solo conserva el motor de templating de CORREO.
Los globals web del legacy (`asset()`, `env_script()`, que servían a las vistas
HTML + el shell de Vite) NO se registran aquí — las plantillas de correo solo
usan `t()` y `app_name` —, así que sus tests no se traen.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jinja2 import UndefinedError

from tequio.Core.View.TemplateEngine import TemplateEngine

_PLACEHOLDER_RE = re.compile(r"%\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _write_template(base: Path, name: str, content: str) -> None:
    target = base / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _make_fake_translate(catalog: dict[str, str]) -> Callable[..., str]:
    """Translate-func fake para tests: lookup directo en `catalog` con
    interpolación `%{name}` (= sintaxis de i18nice).
    Si la key no existe → devuelve la key (mismo contrato que el wrapper real).
    """

    def fake_t(key: str, variables: dict[str, Any] | None = None, locale: str | None = None) -> str:
        template = catalog.get(key)
        if template is None:
            return key
        return _PLACEHOLDER_RE.sub(lambda match: str((variables or {}).get(match.group(1), match.group(0))), template)

    return fake_t


def test_renders_simple_template_with_context(tmp_path: Path) -> None:
    _write_template(tmp_path, "hello.html.j2", "Hola {{ name }}")
    engine = TemplateEngine(templates_dir=tmp_path)

    result = engine.render("hello.html.j2", {"name": "Calcifux"})

    assert result == "Hola Calcifux"


def test_inheritance_extends_and_block_work(tmp_path: Path) -> None:
    """Equivalente al `@extends` + `@section` del Blade legacy (el patrón de los
    correos del demo: cada uno `{% extends %}` el layout firmado compartido)."""
    _write_template(
        tmp_path,
        "layout.html.j2",
        "<html><body>HEADER\n{% block content %}{% endblock %}\nFOOTER</body></html>",
    )
    _write_template(
        tmp_path,
        "child.html.j2",
        '{% extends "layout.html.j2" %}\n{% block content %}Hola {{ name }}{% endblock %}',
    )
    engine = TemplateEngine(templates_dir=tmp_path)

    result = engine.render("child.html.j2", {"name": "Calcifux"})

    assert "HEADER" in result
    assert "Hola Calcifux" in result
    assert "FOOTER" in result


def test_t_global_is_registered_and_interpolates(tmp_path: Path) -> None:
    """El template debe poder llamar `t()` directamente (= `__()` del legacy)."""
    _write_template(
        tmp_path,
        "i18n.html.j2",
        '{{ t("emails/test.hello", {"name": name}, "es") | safe }}',
    )
    translate = _make_fake_translate({"emails/test.hello": "Hola %{name}"})
    engine = TemplateEngine(templates_dir=tmp_path, translate_func=translate)

    result = engine.render("i18n.html.j2", {"name": "Calcifux"})

    assert result == "Hola Calcifux"


def test_safe_filter_keeps_html_unescaped(tmp_path: Path) -> None:
    """El `| safe` equivale al `{!! !!}` de Blade: NO escapa el HTML."""
    _write_template(tmp_path, "safe.html.j2", '{{ t("emails/test.msg", {}, "es") | safe }}')
    translate = _make_fake_translate({"emails/test.msg": "<strong>Hola</strong>"})
    engine = TemplateEngine(templates_dir=tmp_path, translate_func=translate)

    result = engine.render("safe.html.j2", {})

    assert result == "<strong>Hola</strong>"  # SIN escapar


def test_strict_undefined_raises_on_missing_variable(tmp_path: Path) -> None:
    """StrictUndefined hace que un faltante REVIENTE en QA en lugar de
    renderizar vacío en silencio (defense-in-depth contra correos sin datos).
    """
    _write_template(tmp_path, "strict.html.j2", "Hola {{ name }}")
    engine = TemplateEngine(templates_dir=tmp_path, strict_undefined=True)

    with pytest.raises(UndefinedError):
        engine.render("strict.html.j2", {})  # sin pasar `name`
