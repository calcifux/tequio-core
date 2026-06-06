"""Wrapper sobre `i18nice` (PyPI `i18nice`, fork mantenido de `python-i18n`).

Por qué `i18nice` y no un I18n hecho a mano: catálogos YAML, namespaces por
carpetas, pluralización (`one`/`many`/`zero`/`few`), referencias estáticas
(`%{.otra_key}`), funciones custom, memoización. Mantenemos solo este wrapper
para que el resto del código siga llamando `t(key, vars, locale)` (estilo
similar a Laravel `__()`), aislándonos de la firma global de `i18nice`.

Configuración global (la fija este módulo al importarse):
  - load_path:           app/Resources/Lang
  - file_format:         yml (i18nice ya autodescubre archivos `*.yml`).
  - filename_format:     {namespace}.{locale}.{format}  (default de i18nice).
  - skip_locale_root_data: False (los YAML llevan el locale como raíz).
  - fallback:            settings.app_fallback_locale (= "es" por defecto).

Convención de archivos (folders en PascalCase):
    app/Resources/Lang/
      ├── Emails/
      │   ├── master.es.yml          # contiene `es: {...}` al inicio
      │   ├── master.en.yml          # contiene `en: {...}` al inicio
      │   ├── mastersigned.es.yml
      │   └── ...
      └── Api/                       # (futuro) mensajes de respuesta API
          └── ...

Convención de claves (en código):
  - Aceptamos slash y/o punto: `"Emails/master.faq_message"` o
    `"Emails.master.faq_message"`. El wrapper normaliza a la sintaxis de
    `i18nice` (todo con puntos).
  - i18nice infiere el namespace desde el folder y el filename — por eso el
    primer segmento es `Emails` (folder PascalCase), no `emails`.
  - Placeholders en YAML usan `%{name}` (sintaxis de `i18nice`).
"""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Any

import i18n as _i18nice

from tequio.Core.Config import settings
from tequio.Core.Discovery import package_dir

# Locale del REQUEST/contexto actual (scoped vía contextvar). Lo fija quien encola o
# el CLI; `t()` lo usa cuando no se pasa locale explícito. Fuera de un contexto
# (cron, CLI, worker sin restaurar) es None → `t()` cae al app_fallback_locale.
_request_locale: ContextVar[str | None] = ContextVar("request_locale", default=None)


def set_request_locale(locale: str) -> None:
    """Fija el locale del request actual (lo consume `t()` por default)."""
    _request_locale.set(locale)


def current_locale() -> str:
    """Locale del contexto actual (lo fijó quien encola/CLI con `set_request_locale`).

    Sin capa HTTP el locale no se resuelve solo: úsalo para CAPTURAR el locale ya
    fijado y pasarlo a un Mailable que se ENCOLA (el worker no ve el contextvar).
    Fuera de un contexto con locale fijado (cron/CLI/worker) cae al
    `app_fallback_locale`.
    """
    return _request_locale.get() or settings.app_fallback_locale


# Raíz del proyecto y carpeta base de catálogos (compartidos). Absolutas para que
# funcionen igual desde el CLI o desde tests.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # = .../src/tequio (raíz del PAQUETE)
_LANG_DIR = _PROJECT_ROOT / "Resources" / "Lang"


def _module_lang_dirs() -> list[Path]:
    """Descubre los catálogos POR MÓDULO: cada `app/Modules/<X>/Resources/Lang` que
    exista. Convención (carpeta-prefijo): el módulo mete sus YAML bajo una carpeta con
    su prefijo (p. ej. `Resources/Lang/example/Emails/x.es.yml` → key `example.Emails.x`), así
    no chocan namespaces entre módulos (i18nice no tiene prefijo nativo por-path).
    Self-contained: viajan con el módulo al extraerlo."""
    modules_root = package_dir(settings.modules_package)
    if modules_root is None or not modules_root.is_dir():
        return []
    return [
        module_dir / "Resources" / "Lang"
        for module_dir in sorted(modules_root.iterdir())
        if (module_dir / "Resources" / "Lang").is_dir() and not module_dir.name.startswith("_")
    ]


def _configure() -> None:
    """Configura `i18nice` una sola vez por proceso.

    `i18nice` mantiene estado de módulo (igual que las facades de Laravel).
    Idempotente: agregar un mismo path dos veces se evita con un `if not in`.
    """
    # Lang del framework + del USUARIO (si está configurado USER_LANG_DIR) + por módulo.
    user_lang = [Path(settings.user_lang_dir)] if settings.user_lang_dir else []
    for lang_dir in [_LANG_DIR, *user_lang, *_module_lang_dirs()]:
        if lang_dir.is_dir() and str(lang_dir) not in _i18nice.load_path:
            _i18nice.load_path.append(str(lang_dir))
    _i18nice.set("file_format", "yml")
    _i18nice.set("filename_format", "{namespace}.{locale}.{format}")
    _i18nice.set("fallback", settings.app_fallback_locale)
    # placeholder_delimiter='%' → la sintaxis en YAML es `%{name}` (default de
    # i18nice; decisión deliberada: no calcar 1:1 el `:name` de Laravel).
    # Por defecto i18nice deja `on_missing_*` en None: si la traducción falta,
    # arroja `KeyError`. NO queremos eso en correos a usuarios (un faltante no
    # debe tirar el envío). El wrapper captura la excepción y devuelve la key
    # (igual que Laravel `__()` cuando la clave no existe → visible en QA).


_configure()


def t(
    key: str,
    variables: dict[str, Any] | None = None,
    locale: str | None = None,
) -> str:
    """Traduce `key` con `variables` interpoladas, en `locale` (o default).

    Acepta claves con slash o punto como separador de namespace, ej.:
      - "Emails/master.faq_message"
      - "emails.master.faq_message"

    Internamente `i18nice` usa solo puntos; el wrapper hace la conversión.
    Si la clave (o un placeholder) falta, devuelve la propia clave de entrada
    para que el faltante quede VISIBLE en QA sin romper el envío.
    """
    normalized_key = key.replace("/", ".")
    # Prioridad: locale explícito > locale del contexto (set_request_locale) > fallback config.
    effective_locale = locale or _request_locale.get() or settings.app_fallback_locale
    # `app_name` se inyecta SIEMPRE como variable disponible (= la marca del proyecto,
    # desde APP_NAME del .env). Así los catálogos genéricos del framework pueden usar
    # `%{app_name}` (privacy_message, welcome, footer) y resuelven sin que cada
    # llamador lo pase. Si el llamador manda su propio `app_name`, ese gana.
    merged_variables = {"app_name": settings.app_name, **(variables or {})}
    try:
        # `i18nice` acepta `locale=` por llamada (no afecta el global) y los
        # kwargs se interpolan en `%{name}` dentro del string.
        result = _i18nice.t(normalized_key, locale=effective_locale, **merged_variables)
    except KeyError:
        # Clave no encontrada en NINGÚN locale (ni el pedido ni el fallback).
        # Devolvemos la propia key (Laravel `__()` se comporta igual).
        return key
    return str(result)
