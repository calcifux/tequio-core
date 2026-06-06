"""Tests del wrapper `tequio.Core.Translate.I18n.t`.

Estrategia (sin BD ni red):
  - Tests "unit": monkeypatch a `_i18nice.t` para verificar que el wrapper
    normaliza la key (slash → dot), elige el locale correcto, propaga las
    variables, y atrapa KeyError devolviendo la key original.
  - Test "integration" mínimo: cargar un YAML real en `tmp_path` agregándolo
    al `load_path` de i18nice, y traducir end-to-end.

i18nice mantiene estado global (load_path, settings) — el cargador SOLO se
configura una vez al importar `tequio.Core.Translate`, así que en tests con YAML
real usamos namespaces únicos por test para evitar colisiones de caché.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import i18n as _i18nice
import pytest
from pytest import MonkeyPatch

from tequio.Core.Translate import I18n as translate_module
from tequio.Core.Translate import t

# --- Unit tests del wrapper (con mock de i18nice) ---------------------------


def test_t_normalizes_slash_namespace_to_dot(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_t(key: str, **kwargs: Any) -> str:
        captured["key"] = key
        captured["kwargs"] = kwargs
        return "TRANSLATED"

    monkeypatch.setattr(translate_module._i18nice, "t", fake_t)  # type: ignore[attr-defined]
    # `t()` inyecta `app_name` (APP_NAME) como variable disponible siempre; lo
    # fijamos para una aserción determinista.
    monkeypatch.setattr(translate_module.settings, "app_name", "TestApp")  # type: ignore[attr-defined]

    result = t("emails/reminder/general.today_message", {"today": "2026-05-28"}, "es")

    assert result == "TRANSLATED"
    assert captured["key"] == "emails.reminder.general.today_message"
    assert captured["kwargs"] == {"locale": "es", "today": "2026-05-28", "app_name": "TestApp"}


def test_t_uses_default_locale_when_not_specified(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_t(key: str, **kwargs: Any) -> str:
        captured.update(kwargs)
        return ""

    monkeypatch.setattr(translate_module._i18nice, "t", fake_t)  # type: ignore[attr-defined]
    monkeypatch.setattr(translate_module.settings, "app_fallback_locale", "es")  # type: ignore[attr-defined]

    t("emails/test.hello")

    assert captured["locale"] == "es"


def test_t_returns_original_key_when_translation_missing(monkeypatch: MonkeyPatch) -> None:
    """Cuando i18nice no encuentra la clave, lanza KeyError; nuestro wrapper
    debe atraparlo y devolver la KEY ORIGINAL (con slashes, sin normalizar)
    para que el faltante sea visible en QA exactamente como lo escribiste.
    """

    def fake_t(*args: Any, **kwargs: Any) -> str:
        raise KeyError("translation not found")

    monkeypatch.setattr(translate_module._i18nice, "t", fake_t)  # type: ignore[attr-defined]

    result = t("emails/no_existe.foo", {}, "es")

    # La key ORIGINAL (no la normalizada con puntos) para preservar la intención.
    assert result == "emails/no_existe.foo"


def test_t_passes_empty_variables_correctly(monkeypatch: MonkeyPatch) -> None:
    """Sin variables, solo locale debe ir como kwarg a i18nice."""
    captured: dict[str, Any] = {}

    def fake_t(key: str, **kwargs: Any) -> str:
        captured.update(kwargs)
        return ""

    monkeypatch.setattr(translate_module._i18nice, "t", fake_t)  # type: ignore[attr-defined]
    monkeypatch.setattr(translate_module.settings, "app_name", "TestApp")  # type: ignore[attr-defined]

    t("emails/test.hello", locale="en")

    # `app_name` siempre va (inyectado por `t()`); además del locale.
    assert captured == {"locale": "en", "app_name": "TestApp"}


def test_t_returns_string_even_if_i18nice_returns_other_type(monkeypatch: MonkeyPatch) -> None:
    """Defensivo: si i18nice por alguna razón devuelve no-str, garantizamos str."""
    monkeypatch.setattr(translate_module._i18nice, "t", lambda *a, **k: 123)  # type: ignore[attr-defined]  # devuelve int

    result = t("emails/test.foo", {}, "es")

    assert result == "123"
    assert isinstance(result, str)


# --- Integration test con YAML real -----------------------------------------


def test_t_loads_real_yaml_and_interpolates(tmp_path: Path) -> None:
    """End-to-end mínimo con YAML: agregamos un load_path temporal, pedimos
    una traducción, verificamos que i18nice cargó el archivo e interpoló bien.
    """
    # Namespace único por test (basado en nombre del file → evita colisiones
    # con el catálogo del repo en caché global de i18nice).
    namespace = "translate_test_smoke"
    catalog = tmp_path / f"{namespace}.es.yml"
    catalog.write_text("es:\n  hello: 'Hola %{name}'\n", encoding="utf-8")

    _i18nice.load_path.append(str(tmp_path))

    result = t(f"{namespace}.hello", {"name": "Calcifux"}, "es")

    assert result == "Hola Calcifux"


def test_t_falls_back_to_default_locale(tmp_path: Path) -> None:
    """Si el locale pedido no tiene la clave, i18nice cae al fallback (es)."""
    namespace = "translate_test_fallback"
    # Solo escribimos el ES (NO el EN).
    (tmp_path / f"{namespace}.es.yml").write_text("es:\n  saludo: 'Hola'\n", encoding="utf-8")

    _i18nice.load_path.append(str(tmp_path))

    # Pedimos en 'en' (no existe) → cae a ES por fallback configurado en _configure().
    result = t(f"{namespace}.saludo", locale="en")

    assert result == "Hola"


def test_t_supports_keys_with_slashes_natural(tmp_path: Path) -> None:
    """Comprobamos que un namespace tipo `emails/sub/foo` (con slashes) se
    convierte y resuelve correctamente contra carpetas anidadas."""
    namespace_dir = tmp_path / "emails" / "sub"
    namespace_dir.mkdir(parents=True)
    (namespace_dir / "translate_test_nested.es.yml").write_text("es:\n  msg: 'Mensaje'\n", encoding="utf-8")

    _i18nice.load_path.append(str(tmp_path))

    result = t("emails/sub/translate_test_nested.msg", locale="es")

    assert result == "Mensaje"


@pytest.fixture(autouse=True)
def _restore_i18nice_load_path() -> Any:
    """Aísla cada test: snapshotea `load_path` antes y lo restaura después.
    Evita que la lista crezca sin freno entre corridas de la suite.
    """
    snapshot = list(_i18nice.load_path)
    yield
    _i18nice.load_path[:] = snapshot
